import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import logging
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import io

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class SP500GoogleDriveUpdater:
    def __init__(self, csv_filename='sp500_data.csv', folder_name='SP500_Data'):
        self.csv_filename = csv_filename
        self.folder_name = folder_name
        self.symbol = '^GSPC'  # Symbole Yahoo Finance pour S&P 500
        self.service = None
        self.folder_id = None
        
    def authenticate_google_drive(self):
        """Authentification avec Google Drive API"""
        try:
            # Récupérer les credentials depuis les variables d'environnement (GitHub Secrets)
            credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
            if not credentials_json:
                raise ValueError("GOOGLE_CREDENTIALS non trouvé dans les variables d'environnement")
            
            # Convertir JSON string en dictionnaire
            credentials_info = json.loads(credentials_json)
            
            # Créer les credentials
            credentials = Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            
            # Construire le service
            self.service = build('drive', 'v3', credentials=credentials)
            logging.info("✅ Authentification Google Drive réussie")
            return True
            
        except Exception as e:
            logging.error(f"❌ Erreur d'authentification Google Drive : {e}")
            return False
    
    def get_or_create_folder(self):
        """Trouve ou crée le dossier SP500_Data dans Google Drive"""
        try:
            # Chercher le dossier existant
            results = self.service.files().list(
                q=f"name='{self.folder_name}' and mimeType='application/vnd.google-apps.folder'",
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                self.folder_id = folders[0]['id']
                logging.info(f"📁 Dossier '{self.folder_name}' trouvé : {self.folder_id}")
            else:
                # Créer le dossier
                folder_metadata = {
                    'name': self.folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = self.service.files().create(body=folder_metadata, fields='id').execute()
                self.folder_id = folder.get('id')
                logging.info(f"📁 Dossier '{self.folder_name}' créé : {self.folder_id}")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Erreur création/recherche dossier : {e}")
            return False
    
    def get_existing_csv_from_drive(self):
        """Télécharge le CSV existant depuis Google Drive"""
        try:
            # Chercher le fichier CSV dans le dossier
            results = self.service.files().list(
                q=f"name='{self.csv_filename}' and parents in '{self.folder_id}'",
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                file_id = files[0]['id']
                # Télécharger le contenu du fichier
                request = self.service.files().get_media(fileId=file_id)
                file_content = request.execute()
                
                # Convertir en DataFrame
                df = pd.read_csv(io.StringIO(file_content.decode('utf-8')))
                df['Date'] = pd.to_datetime(df['Date']).dt.date
                logging.info(f"📥 CSV existant téléchargé : {len(df)} lignes")
                return df
            else:
                logging.info("📄 Aucun CSV existant trouvé, création d'un nouveau")
                return pd.DataFrame(columns=['Date', 'Opening_Price'])
                
        except Exception as e:
            logging.error(f"❌ Erreur téléchargement CSV : {e}")
            return pd.DataFrame(columns=['Date', 'Opening_Price'])
    
    def upload_csv_to_drive(self, df):
        """Upload le CSV mis à jour vers Google Drive"""
        try:
            # Convertir DataFrame en CSV string
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_content = csv_buffer.getvalue()
            
            # Sauvegarder temporairement le fichier
            with open(self.csv_filename, 'w') as f:
                f.write(csv_content)
            
            # Chercher si le fichier existe déjà
            results = self.service.files().list(
                q=f"name='{self.csv_filename}' and parents in '{self.folder_id}'",
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            
            media = MediaFileUpload(
                self.csv_filename,
                mimetype='text/csv',
                resumable=True
            )
            
            if files:
                # Mettre à jour le fichier existant
                file_id = files[0]['id']
                updated_file = self.service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
                logging.info(f"📤 CSV mis à jour sur Google Drive : {updated_file.get('id')}")
            else:
                # Créer un nouveau fichier
                file_metadata = {
                    'name': self.csv_filename,
                    'parents': [self.folder_id]
                }
                new_file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                logging.info(f"📤 Nouveau CSV créé sur Google Drive : {new_file.get('id')}")
            
            # Nettoyer le fichier temporaire
            os.remove(self.csv_filename)
            return True
            
        except Exception as e:
            logging.error(f"❌ Erreur upload CSV : {e}")
            return False
    
    def get_sp500_opening_price(self, date):
        """Récupère le cours d'ouverture du S&P 500"""
        try:
            end_date = date + timedelta(days=1)
            ticker = yf.Ticker(self.symbol)
            hist = ticker.history(start=date, end=end_date)
            
            if hist.empty:
                logging.warning(f"⚠️ Aucune donnée pour {date}")
                return None
                
            opening_price = hist['Open'].iloc[0]
            logging.info(f"💰 Cours récupéré pour {date}: ${opening_price:.2f}")
            return round(opening_price, 2)
            
        except Exception as e:
            logging.error(f"❌ Erreur récupération cours : {e}")
            return None
    
    def is_trading_day(self, date):
        """Vérifie si c'est un jour de trading (lundi-vendredi)"""
        return date.weekday() < 5  # 0-4 = lundi-vendredi
    
    def get_last_trading_date(self, date):
        """Trouve la dernière date de trading"""
        while not self.is_trading_day(date):
            date = date - timedelta(days=1)
        return date
    
    def update_sp500_data(self):
        """Fonction principale de mise à jour"""
        try:
            logging.info("🚀 Début de la mise à jour S&P 500")
            
            # 1. Authentification Google Drive
            if not self.authenticate_google_drive():
                return False
            
            # 2. Créer/trouver le dossier
            if not self.get_or_create_folder():
                return False
            
            # 3. Télécharger le CSV existant
            df = self.get_existing_csv_from_drive()
            
            # 4. Déterminer la date cible
            today = datetime.now().date()
            target_date = self.get_last_trading_date(today)
            
            # 5. Vérifier si on a déjà cette date
            if not df.empty and target_date in df['Date'].values:
                logging.info(f"📅 Données pour {target_date} déjà présentes")
                return True
            
            # 6. Récupérer le nouveau cours
            opening_price = self.get_sp500_opening_price(target_date)
            if opening_price is None:
                return False
            
            # 7. Ajouter la nouvelle donnée
            new_row = pd.DataFrame({
                'Date': [target_date],
                'Opening_Price': [opening_price]
            })
            
            df = pd.concat([df, new_row], ignore_index=True)
            df = df.sort_values('Date').drop_duplicates(subset=['Date'], keep='last')
            
            # 8. Upload vers Google Drive
            if self.upload_csv_to_drive(df):
                logging.info(f"✅ Mise à jour terminée : {target_date} - ${opening_price}")
                return True
            else:
                return False
                
        except Exception as e:
            logging.error(f"❌ Erreur générale : {e}")
            return False

def main():
    """Point d'entrée principal"""
    updater = SP500GoogleDriveUpdater()
    
    success = updater.update_sp500_data()
    
    if success:
        print("✅ Mise à jour réussie !")
    else:
        print("❌ Échec de la mise à jour")

if __name__ == "__main__":
    main()
