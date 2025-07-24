import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import logging
import json
import requests
from pathlib import Path

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class SP500GitHubUpdater:
    def __init__(self, csv_filename='sp500_data.csv'):
        self.csv_filename = csv_filename
        self.symbol = '^GSPC'  # Symbole Yahoo Finance pour S&P 500
        
    def load_existing_csv(self):
        """Charge le CSV existant depuis le système de fichiers avec nettoyage du format français"""
        try:
            if Path(self.csv_filename).exists():
                df = pd.read_csv(self.csv_filename)
                
                # Nettoyer la colonne Opening_Price (format français avec €, espaces, virgules)
                if 'Opening_Price' in df.columns:
                    df['Opening_Price'] = df['Opening_Price'].astype(str)
                    # Supprimer €, guillemets, espaces
                    df['Opening_Price'] = df['Opening_Price'].str.replace('€', '')
                    df['Opening_Price'] = df['Opening_Price'].str.replace('"', '')
                    df['Opening_Price'] = df['Opening_Price'].str.replace(' ', '')
                    # Remplacer virgule par point pour les décimales
                    df['Opening_Price'] = df['Opening_Price'].str.replace(',', '.')
                    # Convertir en float
                    df['Opening_Price'] = pd.to_numeric(df['Opening_Price'], errors='coerce')
                
                # Convertir les dates (format DD/MM/YYYY)
                df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce').dt.date
                
                # Supprimer les lignes avec des erreurs de conversion
                df = df.dropna()
                
                logging.info(f"📥 CSV existant chargé et nettoyé : {len(df)} lignes")
                return df
            else:
                logging.info("📄 Aucun CSV existant, création d'un nouveau")
                return pd.DataFrame(columns=['Date', 'Opening_Price'])
        except Exception as e:
            logging.error(f"❌ Erreur chargement CSV : {e}")
            return pd.DataFrame(columns=['Date', 'Opening_Price'])
    
    def save_csv(self, df):
        """Sauvegarde le DataFrame en CSV avec formatage propre"""
        try:
            # Créer une copie pour le formatage
            df_save = df.copy()
            
            # Formater les dates au format DD/MM/YYYY
            df_save['Date'] = pd.to_datetime(df_save['Date']).dt.strftime('%d/%m/%Y')
            
            # Formater les prix : 2 décimales, pas de symbole €
            df_save['Opening_Price'] = df_save['Opening_Price'].round(2)
            
            # Sauvegarder en format standard (virgule séparateur, point décimal)
            df_save.to_csv(self.csv_filename, index=False)
            logging.info(f"💾 CSV sauvegardé (format propre) : {len(df)} lignes")
            return True
        except Exception as e:
            logging.error(f"❌ Erreur sauvegarde CSV : {e}")
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
    
    def send_to_webhook(self, df):
        """Envoie les données à un webhook pour synchronisation (optionnel)"""
        try:
            webhook_url = os.environ.get('WEBHOOK_URL')
            if not webhook_url:
                logging.info("📡 Pas de webhook configuré, synchronisation sautée")
                return True
            
            # Convertir en JSON pour l'envoi
            data = {
                'timestamp': datetime.now().isoformat(),
                'latest_price': float(df['Opening_Price'].iloc[-1]),
                'latest_date': df['Date'].iloc[-1].isoformat(),
                'total_records': len(df)
            }
            
            response = requests.post(webhook_url, json=data, timeout=30)
            if response.status_code == 200:
                logging.info("📡 Données envoyées au webhook avec succès")
            else:
                logging.warning(f"⚠️ Webhook répondu avec le code {response.status_code}")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Erreur envoi webhook : {e}")
            # Ne pas faire échouer le processus principal
            return True
    
    def create_public_url_info(self, df):
        """Crée un fichier d'informations pour l'accès public"""
        try:
            # Informations sur le fichier pour un accès facile
            info = {
                'file_name': self.csv_filename,
                'last_updated': datetime.now().isoformat(),
                'total_records': len(df),
                'latest_date': df['Date'].iloc[-1].isoformat() if not df.empty else None,
                'latest_price': float(df['Opening_Price'].iloc[-1]) if not df.empty else None,
                'github_raw_url': f"https://raw.githubusercontent.com/{os.environ.get('GITHUB_REPOSITORY', 'user/repo')}/main/{self.csv_filename}",
                'description': "S&P 500 opening prices updated daily"
            }
            
            with open('sp500_info.json', 'w') as f:
                json.dump(info, f, indent=2)
            
            logging.info("📋 Fichier d'informations créé")
            return True
            
        except Exception as e:
            logging.error(f"❌ Erreur création fichier info : {e}")
            return True  # Non critique
    
    def update_sp500_data(self):
        """Fonction principale de mise à jour"""
        try:
            logging.info("🚀 Début de la mise à jour S&P 500")
            
            # 1. Charger les données existantes
            df = self.load_existing_csv()
            
            # 2. Déterminer la date cible
            today = datetime.now().date()
            target_date = self.get_last_trading_date(today)
            
            # 3. Vérifier si on a déjà cette date
            if not df.empty and target_date in df['Date'].values:
                logging.info(f"📅 Données pour {target_date} déjà présentes")
                return True
            
            # 4. Récupérer le nouveau cours
            opening_price = self.get_sp500_opening_price(target_date)
            if opening_price is None:
                return False
            
            # 5. Ajouter la nouvelle donnée
            new_row = pd.DataFrame({
                'Date': [target_date],
                'Opening_Price': [opening_price]
            })
            
            if df.empty:
                df = new_row
            else:
                df = pd.concat([df, new_row], ignore_index=True)
            
            df = df.sort_values('Date').drop_duplicates(subset=['Date'], keep='last')
            
            # 6. Sauvegarder localement
            if not self.save_csv(df):
                return False
            
            # 7. Créer les informations publiques
            self.create_public_url_info(df)
            
            # 8. Envoyer au webhook si configuré
            self.send_to_webhook(df)
            
            logging.info(f"✅ Mise à jour terminée : {target_date} - ${opening_price}")
            return True
            
        except Exception as e:
            logging.error(f"❌ Erreur générale : {e}")
            return False

def main():
    """Point d'entrée principal"""
    updater = SP500GitHubUpdater()
    
    success = updater.update_sp500_data()
    
    if success:
        print("✅ Mise à jour réussie !")
        # Afficher l'URL publique pour information
        repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
        print(f"📊 CSV accessible à : https://raw.githubusercontent.com/{repo}/main/sp500_data.csv")
    else:
        print("❌ Échec de la mise à jour")

if __name__ == "__main__":
    main()
