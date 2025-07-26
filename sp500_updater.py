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
        """Charge le CSV existant depuis le système de fichiers"""
        try:
            if Path(self.csv_filename).exists():
                df = pd.read_csv(self.csv_filename, sep=';', decimal=',')
                # Gérer les différents formats de date
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce').dt.date
                logging.info(f"📥 CSV existant chargé : {len(df)} lignes")
                return df
            else:
                logging.info("📄 Aucun CSV existant, création d'un nouveau")
                return pd.DataFrame(columns=['Date', 'Opening_Price'])
        except Exception as e:
            logging.error(f"❌ Erreur chargement CSV : {e}")
            return pd.DataFrame(columns=['Date', 'Opening_Price'])
    
    def save_csv(self, df):
        """Sauvegarde le DataFrame en CSV avec formatage pour Google Sheets"""
        try:
            # Convertir les dates au format français pour Google Sheets
            df_formatted = df.copy()
            df_formatted['Date'] = pd.to_datetime(df_formatted['Date']).dt.strftime('%d/%m/%Y')
            
            # S'assurer que les prix sont des nombres avec 2 décimales
            df_formatted['Opening_Price'] = df_formatted['Opening_Price'].round(2)
            
            # Sauvegarder avec séparateur point-virgule pour Google Sheets FR
            df_formatted.to_csv(self.csv_filename, index=False, sep=';', decimal=',')
            logging.info(f"💾 CSV sauvegardé (format FR) : {len(df)} lignes")
            return True
        except Exception as e:
            logging.error(f"❌ Erreur sauvegarde CSV : {e}")
            return False
    
    def get_sp500_data_range(self, start_date, end_date):
        """Récupère les données S&P 500 pour une plage de dates"""
        try:
            ticker = yf.Ticker(self.symbol)
            hist = ticker.history(start=start_date, end=end_date)
            
            if hist.empty:
                logging.warning(f"⚠️ Aucune donnée pour la période {start_date} à {end_date}")
                return None
                
            # Convertir en DataFrame avec les colonnes nécessaires
            data = []
            for date, row in hist.iterrows():
                data.append({
                    'Date': date.date(),
                    'Opening_Price': round(row['Open'], 2)
                })
            
            df = pd.DataFrame(data)
            logging.info(f"💰 {len(df)} cours récupérés pour la période")
            return df
            
        except Exception as e:
            logging.error(f"❌ Erreur récupération cours : {e}")
            return None
    
    def get_sp500_opening_price(self, date):
        """Récupère le cours d'ouverture du S&P 500 pour une date spécifique"""
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
        """Trouve la dernière date de trading avant ou égale à la date donnée"""
        while not self.is_trading_day(date):
            date = date - timedelta(days=1)
            logging.info(f"🔄 {date} n'est pas un jour de trading, recherche du jour précédent...")
        return date
    
    def get_latest_available_data(self):
        """Récupère les données les plus récentes disponibles"""
        try:
            # Essayer les 10 derniers jours pour être sûr d'avoir des données
            end_date = datetime.now().date() + timedelta(days=1)
            start_date = end_date - timedelta(days=10)
            
            data = self.get_sp500_data_range(start_date, end_date)
            if data is not None and not data.empty:
                # Retourner la date la plus récente
                latest_data = data.iloc[-1]
                logging.info(f"📊 Dernière donnée disponible : {latest_data['Date']} - ${latest_data['Opening_Price']}")
                return latest_data['Date'], latest_data['Opening_Price']
            
            return None, None
            
        except Exception as e:
            logging.error(f"❌ Erreur récupération dernières données : {e}")
            return None, None
    
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
                'description': "S&P 500 opening prices updated daily",
                'note': "Data includes weekends using last trading day values"
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
            
            # 2. Déterminer la date d'aujourd'hui
            today = datetime.now().date()
            
            # 3. Vérifier si on a déjà des données pour aujourd'hui
            if not df.empty and today in df['Date'].values:
                logging.info(f"📅 Données pour {today} déjà présentes")
                return True
            
            # 4. Récupérer les dernières données disponibles
            latest_date, latest_price = self.get_latest_available_data()
            
            if latest_date is None or latest_price is None:
                # Si aucune donnée récente n'est disponible, utiliser les dernières données du CSV
                if not df.empty:
                    latest_date = df['Date'].iloc[-1]
                    latest_price = df['Opening_Price'].iloc[-1]
                    logging.info(f"🔄 Utilisation des dernières données du CSV : {latest_date} - ${latest_price}")
                else:
                    logging.error("❌ Aucune donnée disponible")
                    return False
            
            # 5. Ajouter la nouvelle donnée pour aujourd'hui
            new_row = pd.DataFrame({
                'Date': [today],
                'Opening_Price': [latest_price]
            })
            
            if df.empty:
                df = new_row
            else:
                # Supprimer la ligne d'aujourd'hui si elle existe déjà, puis ajouter la nouvelle
                df = df[df['Date'] != today]
                df = pd.concat([df, new_row], ignore_index=True)
            
            df = df.sort_values('Date').drop_duplicates(subset=['Date'], keep='last')
            
            # 6. Sauvegarder localement
            if not self.save_csv(df):
                return False
            
            # 7. Créer les informations publiques
            self.create_public_url_info(df)
            
            # 8. Envoyer au webhook si configuré
            self.send_to_webhook(df)
            
            trading_status = "📈 Jour de trading" if self.is_trading_day(today) else "📅 Weekend/Jour férié (dernière valeur utilisée)"
            logging.info(f"✅ Mise à jour terminée : {today} - ${latest_price} ({trading_status})")
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
