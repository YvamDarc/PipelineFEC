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
        dfs = []

        for file in uploaded_files:
            # 1. Lecture robuste FEC
            df_tmp = pd.read_csv(
                file,
                sep="\t",
                dtype=str,          # <-- TOUT en string pour ne rien casser (dates, comptes, montants FR avec virgule)
                encoding="utf-8",
                engine="python",
            )

            # 2. Nettoyage colonnes standard FEC (strip espaces)
            df_tmp = df_tmp.apply(lambda col: col.str.strip() if col.dtype == "object" else col)

            dfs.append(df_tmp)

        # 3. Concat
        self.df = pd.concat(dfs, ignore_index=True)

        # 4. Conversion des types importants après concat ONLY ONCE

        # --- Date d'écriture comptable
        # On force en datetime au format AAAAMMJJ
        if "EcritureDate" in self.df.columns:
            self.df["EcritureDate"] = pd.to_datetime(
                self.df["EcritureDate"],
                format="%Y%m%d",
                errors="coerce"
            )
        else:
            st.error("La colonne 'EcritureDate' est absente du FEC.")
            return

        # --- PieceDate aussi (souvent utile pour filtrer ou tracer ensuite)
        if "PieceDate" in self.df.columns:
            self.df["PieceDate"] = pd.to_datetime(
                self.df["PieceDate"],
                format="%Y%m%d",
                errors="coerce"
            )

        # --- Montants
        # On remplace les virgules décimales françaises par des points
        for col_montant in ["Debit", "Credit", "Montantdevise"]:
            if col_montant in self.df.columns:
                self.df[col_montant] = (
                    self.df[col_montant]
                    .str.replace(",", ".", regex=False)
                    .str.replace(" ", "", regex=False)
                )
                self.df[col_montant] = pd.to_numeric(self.df[col_montant], errors="coerce")

        # --- CompteNum
        if "CompteNum" in self.df.columns:
            # garder uniquement les 8 premiers caractères comme tu faisais
            self.df["CompteNum"] = self.df["CompteNum"].str[:8]
            self.df["CompteNum"] = pd.to_numeric(self.df["CompteNum"], errors="coerce")
        else:
            st.error("La colonne 'CompteNum' est absente du FEC.")

        # 5. On crée un index temporel propre dès maintenant
        self.df = self.df.sort_values("EcritureDate")
        self.df = self.df.set_index("EcritureDate")

    def process_data(self, start_compte, end_compte, start_date, end_date, min_total, max_total):
        if self.df is None:
            return None, None, None

        # On travaille sur une copie pour ne pas casser self.df
        df_work = self.df.copy()

        # On supprime des colonnes bruit si elles existent
        colonnes_a_supprimer = [
            'EcritureLet', 'DateLet', 'ValidDate', 'Montantdevise', 'Idevise',
            'DateRglt', 'ModeRglt', 'NatOp', 'IdClient', 'Unnamed: 22'
        ]
        df_work = df_work.drop(columns=colonnes_a_supprimer, errors='ignore')

        # Filtre des comptes
        df_work = df_work[
            (df_work['CompteNum'] >= start_compte) &
            (df_work['CompteNum'] <= end_compte)
        ]

        # Colonnes utiles
        colonnes_a_conserver = ['JournalCode', 'JournalLib', 'CompteNum', 'PieceDate', 'Debit', 'Credit']
        df_work = df_work[colonnes_a_conserver]

        # Sécu : si Debit/Credit pas num, on reconvertit (au cas où load_files n'a pas tourné)
        for col_montant in ["Debit", "Credit"]:
            df_work[col_montant] = (
                df_work[col_montant]
                .astype(str)
                .str.replace(",", ".", regex=False)
                .str.replace(" ", "", regex=False)
            )
            df_work[col_montant] = pd.to_numeric(df_work[col_montant], errors="coerce")

        # TOTAL = Crédit - Débit
        df_work['TOTAL'] = df_work['Credit'] - df_work['Debit']

        # Filtre période sur l'INDEX (EcritureDate) qui est déjà en datetime
        df_period = df_work.loc[start_date:end_date]

        # Agrégat journalier
        df_cumule_journalier = (
            df_period
            .groupby(df_period.index)['TOTAL']
            .sum()
            .reset_index()
            .rename(columns={'EcritureDate': 'EcritureDate', 'TOTAL': 'Cumul_TOTAL'})
        )

        # Créer un calendrier continu jour par jour
        all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
        df_all_dates = pd.DataFrame({'EcritureDate': all_dates})

        # Merge pour combler les jours sans écritures
        df_combined = pd.merge(df_all_dates, df_cumule_journalier, on='EcritureDate', how='left')

        # NaN -> 0
        df_combined['Cumul_TOTAL'] = df_combined['Cumul_TOTAL'].fillna(0)

        # Filtre sur seuil min/max
        df_filtered_final = df_combined[
            (df_combined['Cumul_TOTAL'] >= min_total) &
            (df_combined['Cumul_TOTAL'] <= max_total)
        ]

        # --- Graphique matplotlib
        plt.figure(figsize=(14, 7))
        plt.plot(
            df_filtered_final['EcritureDate'],
            df_filtered_final['Cumul_TOTAL'],
            marker='o',
            linestyle='-'
        )
        plt.xlabel('Dates')
        plt.ylabel('Cumul TOTAL (Crédit - Débit)')
        plt.title('Cumul TOTAL par Date')
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()

        img_buf = io.BytesIO()
        plt.savefig(img_buf, format='png')
        img_buf.seek(0)

        # --- Export Excel
        excel_buffer = io.BytesIO()
        df_filtered_final.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)

        return df_filtered_final, img_buf, excel_buffer


# ===== Interface Streamlit ===== #

st.title("Application de Traitement des Écritures Comptables (FEC)")

app = ComptabiliteApp()

uploaded_files = st.file_uploader(
    "Choisissez jusqu'à 6 fichiers FEC (.txt)",
    type=["txt", "csv"],
    accept_multiple_files=True
)

if uploaded_files:
    if len(uploaded_files) > 6:
        st.warning("Vous ne pouvez importer que jusqu'à 6 fichiers.")
    else:
        app.load_files(uploaded_files)

        if app.df is not None and not app.df.empty:
            # bornes comptes
            start_compte = st.number_input("Numéro de compte de début", min_value=0, value=70000000)
            end_compte = st.number_input("Numéro de compte de fin", min_value=0, value=70999999)

            # plage de dates par défaut = min/max du FEC
            start_date_default = app.df.index.min().date()
            end_date_default = app.df.index.max().date()

            start_date_input = st.date_input("Date de début", value=start_date_default)
            end_date_input = st.date_input("Date de fin", value=end_date_default)

            min_total = st.number_input("Seuil minimum pour 'Cumul_TOTAL'", min_value=0, value=0)
            max_total = st.number_input("Seuil maximum pour 'Cumul_TOTAL'", min_value=0, value=25000)

            if st.button("Analyser"):
                df_filtered_final, img_buf, excel_buffer = app.process_data(
                    start_compte,
                    end_compte,
                    start_date_input,
                    end_date_input,
                    min_total,
                    max_total
                )

                if df_filtered_final is not None:
                    st.write("### Résultat filtré jour par jour")
                    st.dataframe(df_filtered_final)

                    st.write("### Graphique du Cumul TOTAL par Date")
                    st.image(img_buf)

                    st.download_button(
                        label="Télécharger le résultat (Excel)",
                        data=excel_buffer,
                        file_name="dfCAHT.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        else:
            st.error("Le FEC semble vide ou illisible.")
