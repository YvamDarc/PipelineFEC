import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io
from datetime import datetime

class ComptabiliteApp:
    def __init__(self):
        self.df = None
        self.df_filtered = None
    
    def load_files(self, uploaded_files):
        # Lire les fichiers en spécifiant le séparateur
        dataframes = []
        for file in uploaded_files:
            df = pd.read_csv(file, sep="\t")
            dataframes.append(df)
        
        # Combiner tous les DataFrames en un seul
        self.df = pd.concat(dataframes)
        
        # Réinitialiser l'index du DataFrame combiné
        self.df.reset_index(drop=True, inplace=True)
        
    def process_data(self, start_compte, end_compte, start_date, end_date, min_total, max_total):
        if self.df is None:
            return None, None, None
        
        # Assurez-vous que la colonne 'EcritureDate' est bien au format datetime
        self.df['EcritureDate'] = pd.to_datetime(self.df['EcritureDate'], format='%Y%m%d')
        
        # Définir 'EcritureDate' comme index du DataFrame
        self.df.set_index('EcritureDate', inplace=True)
        
        # Trier le DataFrame par l'index (EcritureDate) pour obtenir un DataFrame chronologique
        self.df.sort_index(inplace=True)
        
        # Supprimer les colonnes spécifiées
        colonnes_a_supprimer = [
            'EcritureLet', 'DateLet', 'ValidDate', 'Montantdevise', 'Idevise',
            'DateRglt', 'ModeRglt', 'NatOp', 'IdClient', 'Unnamed: 22'
        ]
        self.df = self.df.drop(columns=colonnes_a_supprimer, errors='ignore')
        
        # Convertir les numéros de compte en chaînes de caractères
        self.df['CompteNum'] = self.df['CompteNum'].astype(str)
        
        # Troncature des numéros de compte pour ne garder que les 8 derniers chiffres
        self.df['CompteNum'] = self.df['CompteNum'].str[:8]
        
        # Convertir les numéros de compte tronqués en numériques
        self.df['CompteNum'] = pd.to_numeric(self.df['CompteNum'], errors='coerce')
        
        # Filtrer les lignes où 'CompteNum' est entre start_compte et end_compte
        self.df_filtered = self.df[(self.df['CompteNum'] >= start_compte) & (self.df['CompteNum'] <= end_compte)]
        
        # Liste des colonnes à conserver
        colonnes_a_conserver = ['JournalCode', 'JournalLib', 'CompteNum', 'PieceDate', 'Debit', 'Credit']
        
        # Conserver uniquement les colonnes spécifiées
        self.df_filtered = self.df_filtered[colonnes_a_conserver]
        
        # Convertir les colonnes en chaînes de caractères
        self.df_filtered['Debit'] = self.df_filtered['Debit'].astype(str)
        self.df_filtered['Credit'] = self.df_filtered['Credit'].astype(str)
        
        # Remplacer les virgules par des points pour les colonnes 'Debit' et 'Credit'
        self.df_filtered['Debit'] = self.df_filtered['Debit'].str.replace(',', '.', regex=False)
        self.df_filtered['Credit'] = self.df_filtered['Credit'].str.replace(',', '.', regex=False)
        
        # Convertir les colonnes 'Debit' et 'Credit' en numériques
        self.df_filtered['Debit'] = pd.to_numeric(self.df_filtered['Debit'], errors='coerce')
        self.df_filtered['Credit'] = pd.to_numeric(self.df_filtered['Credit'], errors='coerce')
        
        # Créer la colonne 'TOTAL' comme différence entre 'Credit' et 'Debit'
        self.df_filtered['TOTAL'] = self.df_filtered['Credit'] - self.df_filtered['Debit']
        
        # Assurez-vous que la colonne 'TOTAL' est numérique
        self.df_filtered['TOTAL'] = pd.to_numeric(self.df_filtered['TOTAL'], errors='coerce')
        
        # Filtrer par plage de dates
        self.df_filtered = self.df_filtered.loc[start_date:end_date]
        
        # Grouper les données par date (index) et calculer la somme de la colonne 'TOTAL'
        df_cumule_journalier = self.df_filtered.groupby(self.df_filtered.index)['TOTAL'].sum().reset_index()
        
        # Renommer la colonne de l'index pour plus de clarté
        df_cumule_journalier.rename(columns={df_cumule_journalier.columns[0]: 'EcritureDate', 'TOTAL': 'Cumul_TOTAL'}, inplace=True)
        
        # Créer un DataFrame avec toutes les dates de la plage spécifiée
        all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
        df_all_dates = pd.DataFrame({'EcritureDate': all_dates})
        
        # Fusionner le DataFrame des dates complètes avec le DataFrame filtré
        df_combined = pd.merge(df_all_dates, df_cumule_journalier, on='EcritureDate', how='left')
        
        # Remplacer les valeurs NaN par 0 dans 'Cumul_TOTAL'
        df_combined['Cumul_TOTAL'] = df_combined['Cumul_TOTAL'].fillna(0)
        
        # Supprimer les lignes où 'Cumul_TOTAL' dépasse le maximum ou est inférieur au minimum
        df_filtered_final = df_combined[(df_combined['Cumul_TOTAL'] >= min_total) & (df_combined['Cumul_TOTAL'] <= max_total)]
        
        # Créer le graphique
        plt.figure(figsize=(14, 7))
        plt.plot(df_filtered_final['EcritureDate'], df_filtered_final['Cumul_TOTAL'], marker='o', linestyle='-', color='b')
        plt.xlabel('Dates')
        plt.ylabel('Cumul TOTAL')
        plt.title('Cumul TOTAL par Date')
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Enregistrer le graphique dans un buffer pour l'afficher dans Streamlit
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        
        # Enregistrer le DataFrame final dans un fichier Excel dans un buffer
        excel_buffer = io.BytesIO()
        df_filtered_final.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)
        
        return df_filtered_final, buf, excel_buffer

# Interface Streamlit
st.title("Application de Traitement des Écritures Comptables")

app = ComptabiliteApp()

uploaded_files = st.file_uploader("Choisissez jusqu'à 6 fichiers TXT", type="txt", accept_multiple_files=True)

if uploaded_files:
    if len(uploaded_files) > 6:
        st.warning("Vous ne pouvez importer que jusqu'à 6 fichiers.")
    else:
        app.load_files(uploaded_files)
        
        # Sélection des plages de numéros de comptes
        start_compte = st.number_input("Numéro de compte de début", min_value=0, value=70000000)
        end_compte = st.number_input("Numéro de compte de fin", min_value=0, value=70999999)
        
        # Vérifier si les dates sont disponibles avant la sélection
        if not app.df.empty:
            # Assurez-vous que l'index est au format datetime
            if not pd.api.types.is_datetime64_any_dtype(app.df.index):
                app.df.index = pd.to_datetime(app.df.index)
                
            start_date = app.df.index.min().date()  # Conversion en datetime.date
            end_date = app.df.index.max().date()    # Conversion en datetime.date
            
            # Sélection des plages de dates
            start_date_input = st.date_input("Date de début", value=start_date)
            end_date_input = st.date_input("Date de fin", value=end_date)
            
            # Seuils pour 'Cumul_TOTAL'
            min_total = st.number_input("Seuil minimum pour 'Cumul_TOTAL'", min_value=0, value=0)
            max_total = st.number_input("Seuil maximum pour 'Cumul_TOTAL'", min_value=0, value=25000)
            
            if st.button("Processer les données"):
                df_filtered_final, buf, excel_buffer = app.process_data(start_compte, end_compte, start_date_input, end_date_input, min_total, max_total)
                
                if df_filtered_final is not None:
                    st.write("### DataFrame Cumulé Journalier Filtré")
                    st.dataframe(df_filtered_final)
                    
                    st.write("### Graphique du Cumul TOTAL par Date")
                    st.image(buf)
                    
                    # Ajouter un bouton de téléchargement
                    st.download_button(
                        label="Télécharger le DataFrame en Excel",
                        data=excel_buffer,
                        file_name="dfCAHT.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
