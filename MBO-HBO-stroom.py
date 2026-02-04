"""
app_teller_noemer.py

Streamlit-app voor het berekenen en visualiseren van doorstroom mbo → ho
op basis van TWEE datasets:

1) Teller: herkomst hoger onderwijs (bijv. DUO-bestand 'herkomst hoger onderwijs 20xx')
   - bevat aantallen ho-instroom, uitgesplitst naar herkomst (mbo).

2) Noemer: gediplomeerde mbo-studenten per instelling/sector/niveau/etc.
   - bevat aantallen mbo-gediplomeerden (de populatie waaruit doorstromers komen).

De app:
- laat de gebruiker per dataset de kolommen mappen op functionele labels;
- koppelt de datasets op gekozen join-sleutels (jaar + andere kenmerken);
- rekent doorstroompercentages uit;
- visualiseert deze per jaar, sector, regio, instelling, etc.
"""

import streamlit as st
import pandas as pd
import plotly.express as px


# ======================================================================
#  BASISINSTELLINGEN
# ======================================================================

st.set_page_config(
    page_title="Doorstroom mbo → ho (twee databronnen)",
    layout="wide",
)


st.title("Doorstroom mbo → ho (twee databronnen – teller & noemer)")

st.markdown(
    """
Deze app combineert **twee datasets**:
1. Een dataset met **ho-instroom naar herkomst (mbo)** (teller).
2. Een dataset met **mbo-gediplomeerden** (noemer).

Door kolommen te koppelen aan functionele labels en join-sleutels te kiezen,
wordt een doorstroompercentage mbo → ho berekend en gevisualiseerd.
"""
)


# ======================================================================
#  HULPFUNCTIES
# ======================================================================

def suggest_default(label: str, cols: list) -> str | None:
    """
    Eenvoudige heuristiek om automatisch een kolom voor te stellen
    op basis van (deel van) de naam.
    """
    label_lower = label.lower()
    for c in cols:
        c_lower = c.lower()
        if label_lower in c_lower:
            return c
        if label == "jaar" and ("jaar" in c_lower or "peil" in c_lower):
            return c
        if label.endswith("_instelling") and "brin" in c_lower:
            return c
        if label.endswith("_sector") and (
            "sector" in c_lower or "sectorkamer" in c_lower or "domein" in c_lower
        ):
            return c
        if label.endswith("_regio") and "regio" in c_lower:
            return c
        if label.startswith("aantal") and (
            "aantal" in c_lower or "stud" in c_lower or "count" in c_lower
        ):
            return c
    return None


def mapping_ui(df: pd.DataFrame, mapping_key: str, functionele_labels: dict, titel: str):
    """
    Genereert een UI-blok om kolommen uit df te koppelen aan functionele labels.

    - df: DataFrame met de ruwe data.
    - mapping_key: key in st.session_state waar de mapping wordt opgeslagen.
    - functionele_labels: dict: {label: beschrijving}
    - titel: sectietitel in de UI.
    """
    st.subheader(titel)

    st.markdown(
        """
Koppel de kolommen uit deze dataset aan de functionele labels.
Zo kun je met verschillende DUO-extracten werken zonder de code aan te passen.
"""
    )

    available_cols = df.columns.tolist()

    if mapping_key not in st.session_state:
        st.session_state[mapping_key] = {}

    mapping = st.session_state[mapping_key]

    col_left, col_right = st.columns(2)
    items = list(functionele_labels.items())
    mid = len(items) // 2

    with col_left:
        for label, beschrijving in items[:mid]:
            st.markdown(f"**{label}** – {beschrijving}")
            default_col = mapping.get(label, suggest_default(label, available_cols))
            default_index = (
                (["(geen)"] + available_cols).index(default_col)
                if default_col in available_cols
                else 0
            )
            gekozen = st.selectbox(
                f"Kies kolom voor '{label}'",
                options=["(geen)"] + available_cols,
                index=default_index,
                key=f"{mapping_key}_{label}",
            )
            mapping[label] = None if gekozen == "(geen)" else gekozen

    with col_right:
        for label, beschrijving in items[mid:]:
            st.markdown(f"**{label}** – {beschrijving}")
            default_col = mapping.get(label, suggest_default(label, available_cols))
            default_index = (
                (["(geen)"] + available_cols).index(default_col)
                if default_col in available_cols
                else 0
            )
            gekozen = st.selectbox(
                f"Kies kolom voor '{label}'",
                options=["(geen)"] + available_cols,
                index=default_index,
                key=f"{mapping_key}_{label}",
            )
            mapping[label] = None if gekozen == "(geen)" else gekozen

    st.session_state[mapping_key] = mapping

    st.info(
        "De gekozen kolommen worden gebruikt bij het koppelen en het berekenen "
        "van doorstroompercentages voor deze dataset."
    )

    return mapping


def apply_filter(df: pd.DataFrame, kolomnaam: str, label_text: str, key_prefix: str):
    """
    Generieke filterfunctie voor een DataFrame op een categorische kolom.
    Toont een multiselect en filtert df op de gekozen waarden.
    """
    if kolomnaam not in df.columns:
        return df

    unieke = sorted(df[kolomnaam].dropna().unique().tolist())
    selectie = st.multiselect(
        label_text,
        options=unieke,
        default=unieke,
        key=f"{key_prefix}_{kolomnaam}",
    )
    if selectie:
        return df[df[kolomnaam].isin(selectie)]
    return df


def combine_teller_noemer(
    df_teller: pd.DataFrame,
    df_noemer: pd.DataFrame,
    map_teller: dict,
    map_noemer: dict,
    join_labels_teller: list,
    join_labels_noemer: list,
) -> pd.DataFrame | None:
    """
    Combineert teller- en noemerdataset op basis van labels en mappings.

    - df_teller: DataFrame met ho-instroom (doorstromers).
    - df_noemer: DataFrame met mbo-gediplomeerden (populatie).
    - map_teller: mapping label -> kolomnaam voor teller.
    - map_noemer: mapping label -> kolomnaam voor noemer.
    - join_labels_teller/noemer: lijsten van labels die als join-sleutel dienen.

    Geeft een DataFrame terug met:

    - join-sleutels (jaar, instelling, sector, regio, niveau, etc.)
    - teller (aantal doorstromers)
    - noemer (aantal gediplomeerden)
    - doorstroompercentage
    """

    col_teller = map_teller.get("aantal_ho_instromers")
    col_noemer = map_noemer.get("aantal_mbo_gediplomeerden")

    if not col_teller or not col_noemer:
        return None
    if col_teller not in df_teller.columns or col_noemer not in df_noemer.columns:
        return None

    # Bouw join-sleutels op basis van labels -> kolomnamen
    join_cols_teller = []
    join_cols_noemer = []

    for lbl in join_labels_teller:
        kol = map_teller.get(lbl)
        if kol and kol in df_teller.columns:
            join_cols_teller.append(kol)

    for lbl in join_labels_noemer:
        kol = map_noemer.get(lbl)
        if kol and kol in df_noemer.columns:
            join_cols_noemer.append(kol)

    # Check: lengte join-lijsten moet gelijk zijn (1-op-1 mapping)
    if len(join_cols_teller) == 0 or len(join_cols_teller) != len(join_cols_noemer):
        return None

    # Data kopiëren en eventueel aggregeren op join-sleutels
    t = df_teller.copy()
    n = df_noemer.copy()

    # Aggregatie: sommeer aantallen per join-combinatie
    t_grouped = (
        t.groupby(join_cols_teller)[col_teller]
        .sum()
        .reset_index(name="teller_doorstromers")
    )

    n_grouped = (
        n.groupby(join_cols_noemer)[col_noemer]
        .sum()
        .reset_index(name="noemer_gediplomeerden")
    )

    # Hernoem de join-kolommen in teller/noemer naar generieke namen
    # zodat we ze later makkelijker in grafieken kunnen gebruiken.
    # We houden een mapping bij van generiek_label -> echte kolomnaam.
    generieke_labels = []
    for lbl_t, lbl_n, kol_t, kol_n in zip(
        join_labels_teller, join_labels_noemer, join_cols_teller, join_cols_noemer
    ):
        # gebruik het label (bijv. "jaar", "instelling_mbo") als generieke naam
        generieke = lbl_t  # aanname: zelfde concept
        generieke_labels.append((generieke, kol_t, kol_n))

    # Pas kolomnamen in de gegroepeerde data aan
    for generieke, kol_t, _ in generieke_labels:
        if kol_t in t_grouped.columns:
            t_grouped = t_grouped.rename(columns={kol_t: generieke})

    for generieke, _, kol_n in generieke_labels:
        if kol_n in n_grouped.columns:
            n_grouped = n_grouped.rename(columns={kol_n: generieke})

    # Merge op de generieke join-kolommen
    join_on = [g for g, _, _ in generieke_labels]
    df_join = pd.merge(
        t_grouped,
        n_grouped,
        on=join_on,
        how="inner",  # bewuste keuze: alleen combinaties waar beide data hebben
    )

    # Doorstroompercentage berekenen
    df_join["doorstroompercentage"] = (
        df_join["teller_doorstromers"]
        / df_join["noemer_gediplomeerden"].replace(0, pd.NA)
        * 100
    )

    return df_join


# ======================================================================
#  SIDEBAR: TWEE UPLOADS
# ======================================================================

st.sidebar.header("1. Upload CSV-bestanden")

st.sidebar.markdown("**Teller** – ho-instroom naar herkomst (mbo).")
file_teller = st.sidebar.file_uploader(
    "Kies CSV voor teller (herkomst hoger onderwijs)", type=["csv"], key="uploader_teller"
)

st.sidebar.markdown("**Noemer** – mbo-gediplomeerden.")
file_noemer = st.sidebar.file_uploader(
    "Kies CSV voor noemer (gediplomeerden mbo)", type=["csv"], key="uploader_noemer"
)

df_teller = None
df_noemer = None

if file_teller is not None:
    try:
        df_teller = pd.read_csv(file_teller, sep=",", encoding="utf-8")
    except UnicodeDecodeError:
        df_teller = pd.read_csv(file_teller, sep=",", encoding="latin-1")
    except pd.errors.ParserError:
        df_teller = pd.read_csv(file_teller, sep=";", engine="python")

if file_noemer is not None:
    # Probeer een aantal veelvoorkomende combinaties expliciet
    tried = False
    for enc in ["utf-8", "latin-1", "utf-16", "utf-16le", "utf-16be"]:
        for sep in [",", ";", "\t"]:
            if tried:
                break
            try:
                df_noemer = pd.read_csv(file_noemer, sep=sep, encoding=enc)
                tried = True
            except UnicodeDecodeError:
                continue
            except pd.errors.ParserError:
                continue

    if not tried:
        st.error(
            "Het noemerbestand kon niet worden ingelezen met standaard combinaties "
            "van encoding en delimiter. Controleer het bestand of converteer het eerst "
            "lokaal naar een 'normale' CSV (UTF-8, komma of puntkomma)."
        )



if df_teller is not None and df_noemer is not None:
    st.sidebar.success("Beide bestanden zijn succesvol ingelezen.")
elif df_teller is not None:
    st.sidebar.info("Tellerbestand ingelezen. Upload ook de noemer.")
elif df_noemer is not None:
    st.sidebar.info("Noemerbestand ingelezen. Upload ook de teller.")
else:
    st.info("Upload beide CSV-bestanden in de sidebar om te beginnen.")


# ======================================================================
#  ALS BEIDE DATASETS AANWEZIG ZIJN: VERDER
# ======================================================================

if df_teller is not None and df_noemer is not None:

    # --------------------------------------------------------------
    # Datainspectie
    # --------------------------------------------------------------
    st.header("Gegevensinspectie")

    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.markdown("### Teller (ho-instroom naar herkomst)")
        st.write(f"Rijen: {df_teller.shape[0]}, kolommen: {df_teller.shape[1]}")
        with st.expander("Voorbeeld tellerdata"):
            st.dataframe(df_teller.head())
        with st.expander("Kolommen & datatypes (teller)"):
            st.dataframe(
                pd.DataFrame(
                    {"kolom": df_teller.columns, "dtype": df_teller.dtypes.astype(str)}
                )
            )

    with col_t2:
        st.markdown("### Noemer (mbo-gediplomeerden)")
        st.write(f"Rijen: {df_noemer.shape[0]}, kolommen: {df_noemer.shape[1]}")
        with st.expander("Voorbeeld noemerdata"):
            st.dataframe(df_noemer.head())
        with st.expander("Kolommen & datatypes (noemer)"):
            st.dataframe(
                pd.DataFrame(
                    {"kolom": df_noemer.columns, "dtype": df_noemer.dtypes.astype(str)}
                )
            )

    # --------------------------------------------------------------
    # Kolonnen-mapping voor beide datasets
    # --------------------------------------------------------------
    st.header("2. Koppel kolommen aan functionele labels")

    # Functionele labels teller (ho-instroom)
    labels_teller = {
        "jaar": "Jaar van ho-instroom (cohort / peiljaar)",
        "instelling_mbo": "Herkomstinstelling mbo (indien aanwezig, bijv. BRIN mbo)",
        "instelling_ho": "Ho-instelling (bestemming)",
        "sector_mbo": "Sector/sectorkamer/domein van de mbo-herkomstopleiding",
        "sector_ho": "Sector/domein van ho-opleiding (indien aanwezig)",
        "regio_mbo": "Regio van mbo-instelling (of woonregio student)",
        "regio_ho": "Regio van ho-instelling",
        "niveau_mbo": "Mbo-niveau (bijv. 2, 3, 4)",
        "aantal_ho_instromers": "Aantal ho-instroom (doorstromers, teller)",
    }

    # Functionele labels noemer (mbo-gediplomeerden)
    labels_noemer = {
        "jaar": "Jaar van diplomering mbo (cohort)",
        "instelling_mbo": "Mbo-instelling (BRIN of intern instellings-ID)",
        "sector_mbo": "Sector/sectorkamer/domein mbo",
        "regio_mbo": "Regio van mbo-instelling",
        "niveau_mbo": "Mbo-niveau (bijv. 2, 3, 4)",
        "aantal_mbo_gediplomeerden": "Aantal mbo-gediplomeerden (noemer)",
    }

    col_map1, col_map2 = st.columns(2)

    with col_map1:
        map_teller = mapping_ui(
            df_teller,
            mapping_key="mapping_teller",
            functionele_labels=labels_teller,
            titel="Mapping voor teller (ho-instroom na mbo)",
        )

    with col_map2:
        map_noemer = mapping_ui(
            df_noemer,
            mapping_key="mapping_noemer",
            functionele_labels=labels_noemer,
            titel="Mapping voor noemer (mbo-gediplomeerden)",
        )

    # --------------------------------------------------------------
    # Koppelmogelijkheden (join-sleutels)
    # --------------------------------------------------------------
    st.header("3. Koppelen van datasets (join-sleutels)")

    st.markdown(
        """
Kies op welke **labels** je de teller- en noemerdatasets wilt koppelen.
Bijvoorbeeld:
- alleen op `jaar` (landelijk doorstroompercentage),
- of op `jaar + instelling_mbo`,
- of op `jaar + sector_mbo + niveau_mbo`.

De app vertaalt deze labels naar kolomnamen en voert vervolgens een join uit.
"""
    )

    mogelijke_join_labels = [
        "jaar",
        "instelling_mbo",
        "sector_mbo",
        "regio_mbo",
        "niveau_mbo",
    ]

    geselecteerde_labels = st.multiselect(
        "Kies join-sleutels (labels) voor koppeling teller ↔ noemer:",
        options=mogelijke_join_labels,
        default=["jaar", "sector_mbo", "niveau_mbo"],
        help="Kies minimaal 'jaar', uitbreiden met instelling/sector/regio/niveau voor fijnmaziger analyse.",
    )

    # Voor de teller en noemer gebruiken we dezelfde labels (maar mapping kan naar andere kolomnamen wijzen).
    join_labels_teller = geselecteerde_labels
    join_labels_noemer = geselecteerde_labels

    # --------------------------------------------------------------
    # TABS voor KPI's en visualisaties
    # --------------------------------------------------------------
    tab_kpi, tab_sector, tab_regio, tab_inst, tab_debug = st.tabs(
        [
            "KPI doorstroom",
            "Doorstroom per sector",
            "Doorstroom per regio",
            "Doorstroom per instelling",
            "Debug & ruwe join",
        ]
    )

    # --------------------------------------------------------------
    # Doorstroom-DataFrame (teller+noemer+percentage) maken
    # --------------------------------------------------------------
    df_join = combine_teller_noemer(
        df_teller,
        df_noemer,
        map_teller,
        map_noemer,
        join_labels_teller,
        join_labels_noemer,
    )

    if df_join is None:
        st.warning(
            "Koppelen van teller en noemer is niet gelukt. "
            "Controleer de mapping en of de gekozen join-sleutels in beide datasets aanwezig zijn."
        )
    else:
        # generiek: 'jaar' zou als label aanwezig moeten zijn als we die hebben gekozen
        jaar_label_aanwezig = "jaar" in geselecteerde_labels and "jaar" in df_join.columns

        # ---------------- TAB: KPI doorstroom ----------------
        with tab_kpi:
            st.subheader("KPI doorstroom mbo → ho (gecombineerd)")

            st.markdown(
                """
Hier zie je doorstroompercentages (teller/noemer) op basis van de koppeling.
Je kunt filteren op jaar, sector, regio, niveau en instelling (voor zover aanwezig in de join).
"""
            )

            df_kpi = df_join.copy()

            # Maak filters dynamisch o.b.v. aanwezige kolommen
            filter_cols = []
            for col in ["jaar", "sector_mbo", "regio_mbo", "instelling_mbo", "niveau_mbo"]:
                if col in df_kpi.columns:
                    filter_cols.append(col)

            # Filters tonen in 2 of 3 kolommen afhankelijk van aantal
            if filter_cols:
                n = len(filter_cols)
                cols_filters = st.columns(min(3, n))
                for i, col in enumerate(filter_cols):
                    with cols_filters[i % len(cols_filters)]:
                        df_kpi = apply_filter(
                            df_kpi,
                            col,
                            label_text=f"Filter op {col}",
                            key_prefix=f"kpi_filter_{col}",
                        )

            # Toon KPI-overzicht (aggregatie over eventuele overige dimensies)
            st.markdown("### Overzicht: totaal doorstroompercentage in selectie")

            # Agregeer over alle dimensies, alleen jaar afzonderlijk als aanwezig
            if jaar_label_aanwezig:
                # Toon zowel totaal als tijdreeks
                total = (
                    df_kpi[["teller_doorstromers", "noemer_gediplomeerden"]]
                    .sum()
                    .to_dict()
                )
                totaal_pct = (
                    total["teller_doorstromers"]
                    / total["noemer_gediplomeerden"]
                    * 100
                    if total["noemer_gediplomeerden"] != 0
                    else None
                )

                st.write(
                    f"Totaal doorstroompercentage (alle jaren in selectie): "
                    f"{totaal_pct:.1f}%"
                    if totaal_pct is not None
                    else "Niet te berekenen (noemer = 0 of ontbrekend)."
                )

                # Tijdreeks per jaar
                df_per_jaar = (
                    df_kpi.groupby("jaar")[
                        ["teller_doorstromers", "noemer_gediplomeerden"]
                    ]
                    .sum()
                    .reset_index()
                )
                df_per_jaar["doorstroompercentage"] = (
                    df_per_jaar["teller_doorstromers"]
                    / df_per_jaar["noemer_gediplomeerden"].replace(0, pd.NA)
                    * 100
                )

                st.markdown("#### Doorstroompercentage per jaar")
                st.dataframe(
                    df_per_jaar.style.format(
                        {
                            "doorstroompercentage": "{:.1f}%",
                        }
                    ),
                    use_container_width=True,
                )

                fig_kpi_year = px.line(
                    df_per_jaar,
                    x="jaar",
                    y="doorstroompercentage",
                    markers=True,
                    title="Doorstroompercentage mbo → ho per jaar",
                )
                fig_kpi_year.update_layout(
                    xaxis_title="Jaar",
                    yaxis_title="Doorstroompercentage",
                )
                st.plotly_chart(fig_kpi_year, use_container_width=True)

            else:
                # Geen jaar in join, dan enkel één aggregate KPI
                total = (
                    df_kpi[["teller_doorstromers", "noemer_gediplomeerden"]]
                    .sum()
                    .to_dict()
                )
                totaal_pct = (
                    total["teller_doorstromers"]
                    / total["noemer_gediplomeerden"]
                    * 100
                    if total["noemer_gediplomeerden"] != 0
                    else None
                )

                st.write(
                    f"Totaal doorstroompercentage voor de selectie: "
                    f"{totaal_pct:.1f}%"
                    if totaal_pct is not None
                    else "Niet te berekenen (noemer = 0 of ontbrekend)."
                )

        # ---------------- TAB: Doorstroom per sector ----------------
        with tab_sector:
            st.subheader("Doorstroompercentage per sector")

            if "sector_mbo" not in df_join.columns:
                st.info(
                    "Geen kolom 'sector_mbo' beschikbaar in de join. "
                    "Voeg 'sector_mbo' toe als join-sleutel en map deze in beide datasets."
                )
            else:
                df_sec = df_join.copy()

                # Filters (jaar, regio, niveau, instelling)
                for col in ["jaar", "regio_mbo", "instelling_mbo", "niveau_mbo"]:
                    if col in df_sec.columns:
                        df_sec = apply_filter(
                            df_sec,
                            col,
                            label_text=f"Filter op {col}",
                            key_prefix=f"sector_filter_{col}",
                        )

                # Aggregatie per sector
                df_sec_group = (
                    df_sec.groupby("sector_mbo")[
                        ["teller_doorstromers", "noemer_gediplomeerden"]
                    ]
                    .sum()
                    .reset_index()
                )
                df_sec_group["doorstroompercentage"] = (
                    df_sec_group["teller_doorstromers"]
                    / df_sec_group["noemer_gediplomeerden"].replace(0, pd.NA)
                    * 100
                )

                st.markdown("### Tabel: doorstroompercentage per sector")
                st.dataframe(
                    df_sec_group.style.format(
                        {"doorstroompercentage": "{:.1f}%"}
                    ),
                    use_container_width=True,
                )

                fig_sec = px.bar(
                    df_sec_group,
                    x="sector_mbo",
                    y="doorstroompercentage",
                    title="Doorstroompercentage mbo → ho per sector (mbo-herkomst)",
                )
                fig_sec.update_layout(
                    xaxis_title="Sector mbo",
                    yaxis_title="Doorstroompercentage",
                )
                st.plotly_chart(fig_sec, use_container_width=True)

        # ---------------- TAB: Doorstroom per regio ----------------
        with tab_regio:
            st.subheader("Doorstroom per regio (mbo)")

            if "regio_mbo" not in df_join.columns:
                st.info(
                    "Geen kolom 'regio_mbo' beschikbaar in de join. "
                    "Voeg 'regio_mbo' toe als join-sleutel en map deze in beide datasets "
                    "(bijvoorbeeld op basis van mbo-instelling)."
                )
            else:
                df_reg = df_join.copy()

                # Filters (jaar, sector, niveau, instelling)
                for col in ["jaar", "sector_mbo", "instelling_mbo", "niveau_mbo"]:
                    if col in df_reg.columns:
                        df_reg = apply_filter(
                            df_reg,
                            col,
                            label_text=f"Filter op {col}",
                            key_prefix=f"regio_filter_{col}",
                        )

                df_reg_group = (
                    df_reg.groupby("regio_mbo")[
                        ["teller_doorstromers", "noemer_gediplomeerden"]
                    ]
                    .sum()
                    .reset_index()
                )
                df_reg_group["doorstroompercentage"] = (
                    df_reg_group["teller_doorstromers"]
                    / df_reg_group["noemer_gediplomeerden"].replace(0, pd.NA)
                    * 100
                )

                st.markdown("### Tabel: doorstroompercentage per regio (mbo)")
                st.dataframe(
                    df_reg_group.style.format(
                        {"doorstroompercentage": "{:.1f}%"}
                    ),
                    use_container_width=True,
                )

                fig_reg = px.bar(
                    df_reg_group,
                    x="regio_mbo",
                    y="doorstroompercentage",
                    title="Doorstroompercentage mbo → ho per regio (mbo-herkomst)",
                )
                fig_reg.update_layout(
                    xaxis_title="Regio mbo",
                    yaxis_title="Doorstroompercentage",
                )
                st.plotly_chart(fig_reg, use_container_width=True)

                # Optioneel: matrix mbo-regio → ho-regio (indien beide aanwezig)
                st.markdown("### Optioneel: beweging mbo-regio → ho-regio")
                if "regio_ho" in df_join.columns:
                    df_flow = df_join.copy()
                    df_flow_group = (
                        df_flow.groupby(["regio_mbo", "regio_ho"])[
                            "teller_doorstromers"
                        ]
                        .sum()
                        .reset_index()
                    )
                    fig_flow = px.treemap(
                        df_flow_group,
                        path=["regio_mbo", "regio_ho"],
                        values="teller_doorstromers",
                        title="Aantal doorstromers van mbo-regio naar ho-regio",
                    )
                    st.plotly_chart(fig_flow, use_container_width=True)
                else:
                    st.info(
                        "Geen kolom 'regio_ho' in de join. "
                        "Map deze in de tellerdataset als je regionale bewegingen naar ho-regio wilt tonen."
                    )

        # ---------------- TAB: Doorstroom per instelling ----------------
        with tab_inst:
            st.subheader("Doorstroom per mbo-instelling")

            if "instelling_mbo" not in df_join.columns:
                st.info(
                    "Geen kolom 'instelling_mbo' beschikbaar in de join. "
                    "Voeg 'instelling_mbo' toe als join-sleutel en map deze in beide datasets."
                )
            else:
                df_inst = df_join.copy()

                # Filters (jaar, sector, regio, niveau)
                for col in ["jaar", "sector_mbo", "regio_mbo", "niveau_mbo"]:
                    if col in df_inst.columns:
                        df_inst = apply_filter(
                            df_inst,
                            col,
                            label_text=f"Filter op {col}",
                            key_prefix=f"inst_filter_{col}",
                        )

                df_inst_group = (
                    df_inst.groupby("instelling_mbo")[
                        ["teller_doorstromers", "noemer_gediplomeerden"]
                    ]
                    .sum()
                    .reset_index()
                )
                df_inst_group["doorstroompercentage"] = (
                    df_inst_group["teller_doorstromers"]
                    / df_inst_group["noemer_gediplomeerden"].replace(0, pd.NA)
                    * 100
                )

                st.markdown("### Tabel: doorstroompercentage per mbo-instelling")
                st.dataframe(
                    df_inst_group.style.format(
                        {"doorstroompercentage": "{:.1f}%"}
                    ),
                    use_container_width=True,
                )

                fig_inst = px.bar(
                    df_inst_group,
                    x="instelling_mbo",
                    y="doorstroompercentage",
                    title="Doorstroompercentage mbo → ho per mbo-instelling",
                )
                fig_inst.update_layout(
                    xaxis_title="Mbo-instelling",
                    yaxis_title="Doorstroompercentage",
                )
                st.plotly_chart(fig_inst, use_container_width=True)

        # ---------------- TAB: Debug & ruwe join ----------------
        with tab_debug:
            st.subheader("Debug & ruwe join")

            st.markdown(
                """
In deze tab kun je de ruwe gecombineerde dataset (teller + noemer + percentage)
bekijken om na te gaan of de koppeling goed is gegaan.
"""
            )
            st.dataframe(df_join.head(200), use_container_width=True)

else:
    # Als niet beide bestanden aanwezig zijn, is hierboven al een melding gegeven.
    pass
