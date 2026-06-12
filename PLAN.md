# FluxEU — Plan de build complet

> Visualiseur du marché européen de l'électricité : prix de zone live, **flux d'interconnexion animés** sur carte, capacités vs utilisation, congestion/convergence, mix de production et analytics historiques.

> Ce document est l'unique spec à fournir à Claude Code. Il contient le modèle de domaine, les sources de données (URLs + auth réels, vérifiés 2026), l'architecture, le contrat d'API, les features avec critères d'acceptation, les données de référence de démarrage, l'ordre de build par jalons, les pièges, et un `CLAUDE.md` prêt à coller.

*Nom de projet « FluxEU » = placeholder, renomme librement. Stack alignée sur ton existant : FastAPI / React-TS.*

---

## 0. Vision en 4 lignes

Une SPA qui montre, en quasi temps réel, **l'Europe électrique comme un graphe** : nœuds = bidding zones colorées par prix day-ahead, arêtes = interconnexions avec **arcs animés** dont l'épaisseur ∝ |MW| et le sens = direction du flux. Un *time scrubber* rejoue les dernières 48 h. Autour de la carte : congestion (price spreads), explorateur d'interconnexions, dashboards par zone, Sankey des flux nets, et analytics. Démarre sans clé API (Energy-Charts), monte en puissance avec ENTSO-E.

---

## 1. Modèle de domaine (référentiel pour Claude Code)

Section dense volontairement — sert à fixer le vocabulaire exact et à justifier les métriques calculées. Pas un cours.

### 1.1 Bidding zone (BZ) = unité atomique

Le marché ne raisonne **pas en pays** mais en zones de dépôt. Conséquences structurantes pour l'app :
- L'Italie a ~7 zones (NORD, CNOR, CSUD, SUD, CALA, SICI, SARD), les Nordiques sont splittés (NO1–5, SE1–4, DK1/DK2), l'Allemagne+Luxembourg sont **fusionnés** (DE-LU).
- Chaque BZ a : un **code EIC** (identifiant ENTSO-E, ex. `10YFR-RTE------C`), un/des TSO, un **centroïde** (lat/lon, pour ancrer les arcs) et une **géométrie** (polygone).
- ⚠️ Ne jamais assimiler zone = frontière administrative pour la géométrie (cf. Italie/Nordiques).

### 1.2 Couplage day-ahead (SDAC / EUPHEMIA) → prix & convergence

Le couplage unique day-ahead (SDAC), via l'algo EUPHEMIA, calcule **simultanément** prix de zone et flux transfrontaliers pour maximiser le bien-être social. Lecture pour l'app :
- Quand une frontière n'est **pas saturée** → les prix des deux zones **convergent** (spread ≈ 0).
- Quand elle **sature** → **price spread** ≠ 0 ; la zone exportatrice est moins chère que l'importatrice. Le spread est donc le **signal de congestion** n°1 à visualiser.
- MTU (Market Time Unit) historiquement horaire, **bascule 15 min** en cours au niveau EU → prévoir granularité paramétrable.

### 1.3 Capacité d'échange : NTC/ATC vs Flow-Based

Deux régimes coexistent, à traiter différemment :
- **NTC/ATC** (Net/Available Transfer Capacity) : capacité MW par sens, frontière par frontière. Simple, directement mappable sur une arête. C'est le cas des liaisons DC (vers GB, Nordique↔Continent) et de plusieurs frontières.
- **Flow-Based Market Coupling (FBMC)** : régions **Core** (CWE+CEE, 13 pays) et **Nordic**. La capacité n'est **pas** un NTC par frontière mais un domaine défini par PTDF/RAM sur des éléments critiques de réseau. ⚠️ Pour ces frontières, un « NTC de frontière » n'existe pas proprement → la grandeur fiable à afficher est le **flux mesuré** et, si dispo, la capacité commerciale échangée, pas un ratio flux/NTC inventé.
- Implémentation : champ `capacity_regime: "NTC" | "FLOW_BASED"` sur chaque frontière ; l'UI adapte l'affichage (barre d'utilisation seulement si NTC).

### 1.4 Flux physiques vs échanges commerciaux/programmés

Trois grandeurs distinctes, ne pas les confondre :
- **Flux physique** (mesuré, ENTSO-E doc `A11`/`A26`, Energy-Charts `/cbpf`) : MW réels sur les lignes, lois de Kirchhoff incluses (transit par pays tiers possible).
- **Échange commercial / programmé** (`A09`/scheduled, Energy-Charts `/cbet`) : résultat d'allocation du marché (day-ahead + intraday).
- **Position nette** par zone = somme algébrique des échanges (import−export).
- Choix produit : la carte montre par défaut le **commercial net** (lisible, = résultat marché) avec toggle vers **physique** (réalité réseau). Bien distinguer dans l'UI.

### 1.5 Métriques dérivées à calculer (différenciantes)

- **Price spread** par frontière = `|p_i − p_j|`. Heatmap + leaderboard « frontières les plus congestionnées ».
- **Rente de congestion** (congestion income) ≈ `spread × flux_programmé` sur la frontière → € captés par la congestion, accumulables sur une période.
- **Indice de convergence** de marché : `% d'heures à convergence totale` sur la plaque, ou `std(prix zonaux)` par MTU → KPI d'intégration.
- **Taux d'utilisation** d'une interconnexion (NTC seulement) = `flux / capacité`.
- **Duration curve** d'utilisation / de prix.
- **Net position** & **import/export par voisin**.

### 1.6 Spécificités à coder explicitement

- **GB post-Brexit** : découplé du SDAC → les interconnexions FR-GB, BE-GB, NL-GB, NO-GB, DK1-GB utilisent un couplage explicite/loose volume, pas implicite. Tag `gb_decoupled: true` sur ces frontières (le spread garde du sens, l'« utilisation NTC » reste valide).
- **Market splitting** Nordique : une zone peut se scinder en congestion interne (déjà reflété par le découpage NO/SE).
- **SIDC / intraday** : optionnel v2 (continu + IDA). v1 = day-ahead suffit.
- **Timezone** : ENTSO-E renvoie en UTC ; le marché raisonne CET/CEST. Stocker en **UTC**, afficher en **Europe/Brussels** avec gestion DST. Source d'erreurs n°1.

---

## 2. Sources de données (réelles, vérifiées 2026)

### 2.1 Energy-Charts API — **défaut, sans clé** (Fraunhofer ISE)

Base : `https://api.energy-charts.info/` — JSON, gratuit, pas de token. **C'est ce qui permet de tourner dès J0.** Endpoints utiles :
- `/price?bzn={BZN}&start=&end=` → prix day-ahead spot par bidding zone.
- `/cbpf?country={c}&start=&end=` → **cross-border physical flow** (flux physiques).
- `/cbet?country={c}&start=&end=` → **cross-border electricity trading** (échanges commerciaux).
- `/public_power?country={c}&start=&end=` → production par filière (mix).
- `/signal?postal_code=` / `/total_power` → état réseau / agrégats.
- Timestamps en **unix seconds**. Schémas typés + exemples sur la page racine.

> Limite : granularité zone parfois agrégée pays ; capacités NTC non exposées finement. Suffisant pour la carte, les flux, les prix et le mix. Utiliser pour le **mode démo / fallback**.

### 2.2 ENTSO-E Transparency Platform — **source autoritaire (upgrade)**

- Base REST : `https://web-api.tp.entsoe.eu/api`
- **Auth** : créer un compte sur `https://transparency.entsoe.eu/`, puis **email à `transparency@entsoe.eu`**, objet `RESTful API access`, avec l'email enregistré dans le corps. Token délivré sous ~3 jours ouvrés. (Process confirmé janv. 2026.)
- **Client Python** : `entsoe-py` (package `entsoe`, repo EnergieID). Expose tout ce qu'il faut :
  - `query_day_ahead_prices(zone, start, end)`
  - `query_crossborder_flows(country_from, country_to, start, end)` (physiques)
  - `query_scheduled_exchanges(country_from, country_to, start, end)` (commerciaux/programmés)
  - `query_net_position(zone, start, end, dayahead=True)`
  - `query_generation(zone, start, end, psr_type=None)` (mix par filière)
  - `query_load(zone, start, end)`
  - `query_net_transfer_capacity_dayahead(...)` / forecast (NTC)
- **Doc types** (si appel REST brut) : `A44` prix day-ahead, `A11`/`A26` flux physiques, `A09`/`A25` échanges programmés/capacité, `A61` NTC forecast, `A75` génération par type, `A65` load.
- **Limites** : 1 requête ≤ 1 an ; max 100 TimeSeries/réponse ; rate-limit (~400 req/min). → impose une couche de cache + backfill (cf. §3.3).
- 🔑 **`entsoe-py` embarque le référentiel autoritaire des zones et frontières** dans `entsoe/mappings.py` : enum `Area` (codes EIC corrects, maintenus) + dict **`NEIGHBOURS`** (quelles zones sont adjacentes). **Utiliser ça comme source de vérité pour construire le graphe d'interconnexions — ne pas hardcoder les codes EIC de mémoire.**

### 2.3 Electricity Maps — optionnel (intensité carbone)

`https://app.electricitymaps.com/developer-hub` — intensité CO₂ + mix flow-traced + flux. Free tier limité (1 zone), commercial au-delà. Brancher seulement pour la couche « carbone » d'un dashboard zone. Non bloquant.

### 2.4 Données géographiques (géométries + centroïdes)

- **v1 (pays)** : Natural Earth / `world-atlas` (TopoJSON) → polygones pays, rapide.
- **v2 (vraies bidding zones)** : géométries de zones (Italie/Nordiques splittés). Candidats : geometries de zones du repo `electricitymaps-contrib` (`web/geo/world.geojson`), ou la carte officielle des bidding zones ENTSO-E. **À valider/charger en build** ; fournir un `zones.geojson` dans `/data`.
- **Centroïdes** : nécessaires pour ancrer les arcs (un par zone). Starter au §6 ; raffiner depuis la géométrie (centroïde du polygone via `turf.centroid` / shapely).

### 2.5 Référence/inspiration

- **Ember — Europe Electricity Interconnection Data Tool** : carte capacités+flux déjà existante → benchmark UX et données de capacité projetées (2030/2040). Ne pas copier, s'en inspirer.

---

## 3. Architecture

### 3.1 Stack

**Backend** — FastAPI (Python 3.11+)
- Data : `entsoe-py` + `httpx` (Energy-Charts) ; `pandas` pour transforms.
- Persistance/analytics : **DuckDB** (embarqué, excellent time-series/agrégats) pour l'historique ; cache live en mémoire à TTL (`cachetools`) ou Redis si tu veux multi-instance.
- Scheduler : `APScheduler` — job de refresh live (5–15 min) + backfill historique.
- Validation : Pydantic v2 (modèles typés en sortie d'API).

**Frontend** — React + TypeScript + **Vite**
- Carte + flux : **deck.gl** (`ArcLayer` pour les flux animés, `GeoJsonLayer` pour les zones colorées) au-dessus d'un basemap **MapLibre GL**. C'est le combo canonique pour des arcs directionnels animés et performants (GPU). *Animation des arcs : dash/trips animé via `getSourcePosition/getTargetPosition` + `currentTime` uniform, ou `TripsLayer` pour l'effet « particules ».*
- Charts : **Recharts** (séries temporelles, ton habitude) + **ECharts** (ou `@nivo`) pour **Sankey** et **heatmap matricielle** des spreads.
- Données/cache front : **TanStack Query** (refetch interval pour le live, invalidation, stale-while-revalidate).
- Styling : **Tailwind CSS**. Transitions : Framer Motion.
- Échelles couleur : `d3-scale-chromatic` (palettes perceptuellement uniformes).

**Infra** — `docker-compose` (backend + front + DuckDB volume) → run en une commande.

### 3.2 Schéma du repo (monorepo)

```
fluxeu/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                # FastAPI app + CORS + routers
│  │  ├─ config.py              # settings (.env: ENTSOE_API optionnel, DATA_SOURCE)
│  │  ├─ sources/
│  │  │  ├─ base.py             # interface DataSource (Protocol)
│  │  │  ├─ energy_charts.py    # impl httpx (défaut, no key)
│  │  │  └─ entsoe.py           # impl entsoe-py (si token présent)
│  │  ├─ domain/
│  │  │  ├─ zones.py            # chargement Area/NEIGHBOURS + centroïdes
│  │  │  ├─ interconnectors.py  # graphe frontières + métadonnées statiques
│  │  │  └─ metrics.py          # spread, congestion rent, convergence index
│  │  ├─ store/
│  │  │  ├─ duckdb_store.py     # schéma + upsert + requêtes agrégées
│  │  │  └─ cache.py            # TTL cache live
│  │  ├─ jobs/scheduler.py      # APScheduler: refresh + backfill
│  │  ├─ models.py              # Pydantic (réponses API)
│  │  └─ routers/               # prices.py, flows.py, interconnectors.py, zones.py, analytics.py
│  ├─ tests/                    # pytest: transforms, metrics, source mapping
│  ├─ requirements.txt
│  └─ Dockerfile
├─ frontend/
│  ├─ src/
│  │  ├─ App.tsx
│  │  ├─ api/                   # client typé (zod) vers le backend
│  │  ├─ map/                   # MapView, ZonesLayer, FlowArcsLayer, TimeScrubber, Legend
│  │  ├─ panels/                # CongestionPanel, InterconnectorExplorer, ZoneDashboard, FlowSankey, Analytics
│  │  ├─ components/            # primitives UI (Card, Stat, Sparkline...)
│  │  ├─ hooks/                 # useLiveSnapshot, useTimeseries (TanStack Query)
│  │  ├─ theme/                 # tokens couleur/typo
│  │  └─ types.ts               # interfaces partagées (miroir des modèles backend)
│  ├─ index.html
│  ├─ package.json
│  └─ Dockerfile
├─ data/
│  ├─ zones.geojson             # géométries bidding zones
│  ├─ zones.json                # EIC, nom, pays, centroïde, TSO, capacity_regime
│  └─ interconnectors.json      # frontières + métadonnées (câbles DC, capacité, année…)
├─ docker-compose.yml
├─ CLAUDE.md                    # cf. §9
└─ README.md
```

### 3.3 Flux de données (ingestion → API → front)

1. **Ingestion** : job APScheduler appelle la `DataSource` active (Energy-Charts par défaut, ENTSO-E si token) → normalise → **upsert DuckDB** (historique) + **TTL cache** (snapshot live).
2. **Backfill** initial : au boot, charger N jours d'historique (respect des limites ENTSO-E : fenêtres ≤ 1 an, pagination par TimeSeries, backoff exponentiel — `entsoe-py` gère déjà le retry).
3. **API** : routers servent (a) un **snapshot live** consolidé pour la carte, (b) des **séries temporelles** par zone/frontière, (c) des **agrégats analytics** (calculés en SQL DuckDB).
4. **Front** : TanStack Query poll le snapshot (interval = refresh backend), le scrubber requête les séries 48 h, les panels requêtent à la demande.

### 3.4 Modèle de données

**Pydantic (backend, extrait)**

```python
class Zone(BaseModel):
    code: str            # EIC, ex "10YFR-RTE------C"
    key: str             # short, ex "FR", "IT-NORD", "SE3"
    name: str
    country: str
    centroid: tuple[float, float]   # (lon, lat)
    tso: list[str]
    capacity_regime: Literal["NTC", "FLOW_BASED"]

class PricePoint(BaseModel):
    zone: str            # key
    ts: datetime         # UTC
    eur_mwh: float

class FlowEdge(BaseModel):
    from_zone: str
    to_zone: str
    ts: datetime
    commercial_mw: float | None   # signé: + = from→to
    physical_mw: float | None
    ntc_mw: float | None          # null si FLOW_BASED
    capacity_regime: Literal["NTC", "FLOW_BASED"]

class LiveSnapshot(BaseModel):
    ts: datetime
    prices: dict[str, float]                 # key -> eur_mwh
    edges: list[FlowEdge]
    net_positions: dict[str, float]          # key -> MW (+import / -export, à fixer & documenter)
    generation_mix: dict[str, dict[str, float]] | None  # key -> {fuel: MW}

class BorderMetric(BaseModel):
    from_zone: str; to_zone: str
    spread_eur_mwh: float
    congestion_income_eur: float | None
    utilisation: float | None     # 0..1, NTC only
```

**TypeScript (frontend, miroir)** — mêmes interfaces dans `types.ts` (générer via `datamodel-codegen`/zod ou maintenir à la main, mais **garder strictement synchrone**).

### 3.5 Contrat d'API (REST)

| Méthode | Route | Réponse | Usage |
|---|---|---|---|
| GET | `/api/zones` | `Zone[]` | métadonnées + géométrie refs |
| GET | `/api/interconnectors` | `Interconnector[]` | frontières + métadonnées câbles |
| GET | `/api/snapshot/live` | `LiveSnapshot` | **carte** (prix + arcs + positions) |
| GET | `/api/snapshot?ts=ISO` | `LiveSnapshot` | scrubber (instant T) |
| GET | `/api/prices?zone=&from=&to=` | `PricePoint[]` | série prix |
| GET | `/api/flows?from=&to=&start=&end=` | `FlowEdge[]` | série flux d'une frontière |
| GET | `/api/zones/{key}/dashboard?from=&to=` | objet agrégé | dashboard zone (prix, load, mix, voisins) |
| GET | `/api/metrics/congestion?ts=` | `BorderMetric[]` | heatmap + leaderboard |
| GET | `/api/metrics/convergence?from=&to=` | série indice | KPI intégration |
| GET | `/api/sankey?ts=` | nodes+links | Sankey flux nets |
| GET | `/api/export.csv?...` | text/csv | download analytics |
| GET | `/api/health` | `{status, source, last_refresh}` | statut + source active |

CORS ouvert au front en dev. Réponses datées en **UTC ISO-8601**.

---

## 4. Fonctionnalités (avec critères d'acceptation)

### 4.1 Carte live — *hero* ⭐

- Carte d'Europe (MapLibre dark basemap), zones (`GeoJsonLayer`) **colorées par prix day-ahead** courant (échelle €/MWh, palette continue + gestion **prix négatifs** distincte, ex. teinte froide saturée).
- **Arcs animés** (`ArcLayer`/`TripsLayer`) entre centroïdes : épaisseur ∝ `|MW|`, **sens animé** = direction du flux, couleur = intensité ou zone source. Toggle **Commercial ⇄ Physique**.
- **Time scrubber** (slider 48 h, + play/pause, vitesse) → rejoue prix+flux ; pré-charge la fenêtre côté front, interpole l'affichage.
- Hover zone → tooltip : prix, position nette, mini-donut mix, charge.
- Hover/clic arc → panneau frontière : flux courant, NTC & utilisation (si NTC), price spread, rente de congestion ; lien vers détail (§4.3).
- Légende + sélecteur de date.
- **DoD** : au chargement, prix réels + ≥ 15 arcs cohérents ; scrubber fluide (≥ 30 fps) sur 48 h ; toggle commercial/physique fonctionne ; prix négatifs visuellement distincts.

### 4.2 Convergence / congestion

- **Heatmap matricielle** des price spreads entre zones (clic cellule → frontière).
- **Leaderboard** « frontières les plus congestionnées maintenant » (spread décroissant) + rente de congestion.
- **Courbe d'indice de convergence** (std prix zonaux ou % heures convergées) sur période choisie.
- **DoD** : la matrice met en évidence ≥ les frontières réellement saturées du jour ; cohérence spread↔direction de flux.

### 4.3 Explorateur d'interconnexions

- Table cherchable/filtrable : toutes les frontières + câbles DC nommés (IFA, IFA2, ElecLink, BritNed, NemoLink, NSL, Viking, NorNed, NordLink, COBRA, EstLink, NordBalt, INELFE…) avec capacité, techno (HVAC/HVDC), longueur, année, propriétaire, **utilisation live**.
- **Page détail/frontière** : séries **flux physique vs programmé**, **NTC vs flux**, **duration curve** d'utilisation, **price spread overlay**, rente de congestion cumulée.
- **DoD** : recherche fonctionne ; page détail trace ≥ 7 j d'historique ; FBMC → pas de barre d'utilisation factice (affiche « flow-based », capacité commerciale si dispo).

### 4.4 Dashboard zone/pays

- Par zone : courbe prix, courbe charge, **stack de production par filière** (area chart), position nette, **imports/exports par voisin** (barres empilées ou Sankey local), part renouvelable, intensité carbone (si Electricity Maps).
- **DoD** : sélection de zone met tout à jour ; mix par filière cohérent avec le total ; voisins corrects (depuis `NEIGHBOURS`).

### 4.5 Sankey des flux Europe

- Sankey des **flux nets** transfrontaliers pour l'instant/jour choisi : qui exporte vers qui, d'un coup d'œil.
- **DoD** : conservation de flux respectée (somme entrées−sorties par nœud cohérente avec positions nettes).

### 4.6 Analytics historique

- Plage de dates, comparaison multi-zones, **export CSV**. Price **duration curves**, **matrice de corrélation** des prix zonaux, patterns saisonniers.
- **DoD** : export CSV valide ; corrélations calculées en SQL DuckDB ; rendu < 2 s sur 1 mois.

### 4.7 (Optionnel) Module Modélisation — *tie-in ton existant*

- Onglet avancé : overlay **prix simulés/forward vs réalisés**. Brancher ton simulateur merit-order + OU (repo EDF-SA) et/ou `peakero-forecaster` (forward curves probabilistes) → comparer courbe forward modélisée et spot réalisé par zone, bandes de confiance.
- Sandbox scénario : choc d'offre/demande → re-dispatch → impact prix/flux (réutilise ta logique de dispatch).
- **DoD** : un endpoint `/api/model/forward?zone=` renvoie une courbe ; overlay s'affiche au-dessus du spot.

### 4.8 (Optionnel) Alertes / signaux

- Détection **prix négatifs** (sur-offre renouvelable), **spikes**, **frontières à pleine capacité**. Badge + flux d'événements.

---

## 5. Direction Design / UX (portable, opinionée)

But : ça doit ressembler à un **terminal de marché énergie**, pas à un dashboard générique.

- **Thème sombre** par défaut (ardoise/charbon `#0B0E14`–`#11151F`), surfaces en cartes à faible contraste, 1 accent électrique (cyan/électrique `#3DE0E0` ou ambre selon export/import).
- **Densité de données** assumée : petites stats numériques, sparklines, mono pour les chiffres (`JetBrains Mono`/`IBM Plex Mono`), sans-serif lisible pour le texte (`Inter`).
- **Couleur = sémantique** : prix bas→haut sur palette perceptuellement uniforme ; **export = teinte A, import = teinte B** constants partout ; prix négatifs traités à part (ne pas les écraser dans la rampe).
- **Mouvement au service de l'info** : arcs animés = flux réel, pas décoratif ; transitions Framer Motion sobres ; skeletons au chargement, error boundaries propres.
- **Accessibilité** : palettes daltonien-safe (éviter rouge/vert seuls), contrastes AA, états hover **et** focus.
- Layout : carte plein cadre en hero, panneaux en *drawer*/onglets latéraux, scrubber sticky en bas.
- Claude Code : appliquer des principes de design intentionnel (typo, hiérarchie, tokens) — pas de défaut « templated ».

---

## 6. Données de référence de démarrage

> ⚠️ **Source de vérité des codes EIC = `entsoe-py` `entsoe/mappings.py` (enum `Area` + `NEIGHBOURS`).** Le tableau ci-dessous est un **starter haute-confiance** pour amorcer `/data/zones.json` et **valider** le chargement ; Claude Code **doit** régénérer/compléter programmatiquement depuis `entsoe-py` (et corriger toute divergence) plutôt que de figer ces strings. Centroïdes = approx. pour l'ancrage des arcs, à raffiner depuis la géométrie.

### Zones principales (starter)

| key | EIC (à confirmer via entsoe-py) | pays | centroïde (lat, lon) | régime |
|---|---|---|---|---|
| FR | 10YFR-RTE------C | France | 46.6, 2.4 | FLOW_BASED (Core) |
| DE-LU | 10Y1001A1001A82H | Allemagne+Lux | 51.1, 10.4 | FLOW_BASED (Core) |
| BE | 10YBE----------2 | Belgique | 50.6, 4.6 | FLOW_BASED (Core) |
| NL | 10YNL----------L | Pays-Bas | 52.2, 5.3 | FLOW_BASED (Core) |
| AT | 10YAT-APG------L | Autriche | 47.6, 14.1 | FLOW_BASED (Core) |
| CH | 10YCH-SWISSGRIDZ | Suisse | 46.8, 8.2 | NTC (hors couplage) |
| ES | 10YES-REE------0 | Espagne | 40.2, -3.7 | NTC |
| PT | 10YPT-REN------W | Portugal | 39.6, -8.0 | NTC |
| IT-NORD | 10Y1001A1001A73I | Italie Nord | 45.5, 9.5 | FLOW_BASED/NTC* |
| IT-CSUD | 10Y1001A1001A71M | Italie C-Sud | 41.9, 12.5 | * |
| IT-SUD | 10Y1001A1001A788 | Italie Sud | 40.5, 16.0 | * |
| IT-SICI | 10Y1001A1001A75E | Sicile | 37.5, 14.0 | * |
| IT-SARD | 10Y1001A1001A74G | Sardaigne | 40.0, 9.0 | * |
| PL | 10YPL-AREA-----S | Pologne | 52.1, 19.4 | FLOW_BASED (Core) |
| CZ | 10YCZ-CEPS-----N | Tchéquie | 49.8, 15.5 | FLOW_BASED (Core) |
| SK | 10YSK-SEPS-----K | Slovaquie | 48.7, 19.7 | FLOW_BASED (Core) |
| HU | 10YHU-MAVIR----U | Hongrie | 47.2, 19.5 | FLOW_BASED (Core) |
| SI | 10YSI-ELES-----O | Slovénie | 46.1, 14.8 | FLOW_BASED (Core) |
| HR | 10YHR-HEP------M | Croatie | 45.1, 15.5 | FLOW_BASED (Core) |
| RO | 10YRO-TEL------P | Roumanie | 45.9, 25.0 | FLOW_BASED (Core) |
| GB | 10YGB----------A | Grande-Bretagne | 54.0, -2.5 | NTC (gb_decoupled) |
| IE-SEM | 10Y1001A1001A59C | Irlande (SEM) | 53.4, -8.0 | NTC |
| DK1 | 10YDK-1--------W | Danemark Ouest | 56.2, 9.0 | NTC/FB Nordic |
| DK2 | 10YDK-2--------M | Danemark Est | 55.5, 12.0 | NTC/FB Nordic |
| NO2 | 10YNO-2--------T | Norvège SO | 58.5, 7.5 | Nordic |
| SE3 | 10Y1001A1001A46L | Suède Centre | 59.3, 16.0 | Nordic |
| SE4 | 10Y1001A1001A47J | Suède Sud | 56.0, 14.0 | Nordic |
| FI | 10YFI-1--------U | Finlande | 64.0, 26.0 | Nordic |
| EE | 10Y1001A1001A39I | Estonie | 58.6, 25.0 | Baltic |
| LV | 10YLV-1001A00074 | Lettonie | 56.9, 24.6 | Baltic |
| LT | 10YLT-1001A0008Q | Lituanie | 55.2, 23.9 | Baltic |

\* Italie/Nordiques : régime à confirmer (zones internes + frontières mixtes) → laisser `metrics.py` traiter au flux mesuré par défaut.

(Compléter NO1/3/4/5, SE1/2, GR, BG, RS/Balkans, etc. depuis `entsoe-py`.)

### Interconnexions DC majeures (faits stables — starter `interconnectors.json`)

| câble | frontière | MW | techno | année | note |
|---|---|---|---|---|---|
| IFA | FR–GB | 2000 | HVDC | 1986 | |
| IFA2 | FR–GB | 1000 | HVDC | 2021 | |
| ElecLink | FR–GB | 1000 | HVDC | 2022 | tunnel sous la Manche |
| BritNed | GB–NL | 1000 | HVDC | 2011 | |
| Nemo Link | GB–BE | 1000 | HVDC | 2019 | |
| North Sea Link | GB–NO2 | 1400 | HVDC | 2021 | |
| Viking Link | GB–DK1 | 1400 | HVDC | 2023 | montée en puissance |
| East-West (EWIC) | GB–IE | 500 | HVDC | 2012 | |
| Greenlink | GB–IE | 500 | HVDC | 2024 | |
| Moyle | GB–IE(NI) | 500 | HVDC | 2001 | |
| NorNed | NO2–NL | 700 | HVDC | 2008 | |
| NordLink | NO2–DE | 1400 | HVDC | 2021 | |
| Skagerrak | NO2–DK1 | ~1700 | HVDC | multi | |
| COBRAcable | DK1–NL | 700 | HVDC | 2019 | |
| Kontek | DK2–DE | 600 | HVDC | 1996 | |
| SwePol | SE4–PL | 600 | HVDC | 2000 | |
| NordBalt | SE4–LT | 700 | HVDC | 2016 | |
| EstLink 1+2 | FI–EE | 1000 | HVDC | 2007/14 | |
| LitPol | LT–PL | 500 | HVAC/DC | 2015 | |
| INELFE | ES–FR | 2×1000 | HVDC | 2015 | + lignes AC |
| GRITA | IT–GR | 500 | HVDC | 2002 | |
| MONITA | IT–ME | 600 | HVDC | 2019 | |
| Celtic | FR–IE | 700 | HVDC | ~2026 | **en construction** |

(Les frontières AC continentales = paires de zones adjacentes via `NEIGHBOURS`, régime FBMC → capacité non listée, flux mesuré.)

---

## 7. Plan de build par jalons (ordre exécutable)

> Chaque jalon est **vérifiable** seul. Construire dans cet ordre ; ne pas avancer si le DoD du jalon n'est pas vert.

- **M0 — Scaffold.** Monorepo, `docker-compose`, FastAPI `health`, Vite+React+TS+Tailwind, MapLibre dark qui rend l'Europe. ✅ quand `docker compose up` sert front+back et la carte s'affiche.
- **M1 — Référentiel zones/frontières.** Charger `entsoe-py` `Area`/`NEIGHBOURS` → générer `data/zones.json` + `data/interconnectors.json` (fusionner starter §6), récupérer `zones.geojson`, calculer centroïdes manquants. Endpoints `/api/zones`, `/api/interconnectors`. ✅ quand les zones s'affichent en polygones et les paires de frontières sont correctes.
- **M2 — Source Energy-Charts (no key) + snapshot live.** Impl `energy_charts.py`, normalisation, TTL cache, `/api/snapshot/live`. ✅ quand prix réels + flux réels reviennent en JSON daté UTC.
- **M3 — Carte live (hero).** Zones colorées par prix + `ArcLayer` flux animés + toggle commercial/physique + tooltips. ✅ critères §4.1 (hors scrubber).
- **M4 — Historique DuckDB + scrubber + séries.** Backfill 48 h–30 j, `/api/snapshot?ts=`, `/api/prices`, `/api/flows`, time scrubber animé. ✅ scrubber fluide + séries tracées.
- **M5 — Métriques & panels.** `metrics.py` (spread, rente, convergence), Congestion panel (heatmap+leaderboard), Interconnector explorer + page détail, Zone dashboard, Sankey. ✅ critères §4.2–4.5.
- **M6 — Analytics + polish + ENTSO-E upgrade.** Export CSV, duration/corrélations, design pass complet, **brancher `entsoe.py`** si token (sélection auto de source via `/api/health`), tests pytest/Vitest, README. ✅ DoD global §10.
- **M7 (option)** — Module modélisation (§4.7) + alertes (§4.8).

---

## 8. Pièges & points de vigilance (à lire avant de coder)

1. **Timezone/DST** : tout stocker en **UTC**, afficher en `Europe/Brussels`. ENTSO-E = UTC, Energy-Charts = unix sec. Les bugs de décalage horaire sont la 1ʳᵉ cause d'erreur ici.
2. **FBMC ≠ NTC** : ne pas fabriquer un « taux d'utilisation » sur une frontière flow-based. Champ `capacity_regime` → l'UI masque la barre d'utilisation et affiche le flux.
3. **Flux physique ≠ commercial** : deux endpoints, deux sens possibles, transit par pays tiers. Documenter la **convention de signe** (`+ = from→to`) et la tenir partout.
4. **GB découplé** : tagger `gb_decoupled`; l'« utilisation NTC » reste valide (couplage explicite), mais ne pas attendre la même mécanique de convergence implicite que sur la plaque.
5. **Italie/Nordiques** : zones internes multiples → géométrie sous-pays obligatoire en v2, sinon les flux internes sont faux. v1 peut agréger au pays en l'assumant explicitement dans l'UI.
6. **Limites ENTSO-E** : fenêtres ≤ 1 an, 100 TS/réponse, rate-limit. Paginer, cacher, backoff (`entsoe-py` retry intégré). Ne **jamais** committer le token (`.env`, `.gitignore`).
7. **Codes EIC** : ne pas les hardcoder de mémoire → `entsoe-py mappings`. Le starter §6 sert à amorcer/valider, pas à figer.
8. **Prix négatifs** : fréquents (renouvelable) → ne pas les écraser dans la rampe couleur ; les rendre distincts.
9. **Centroïdes** : un arc mal ancré = carte moche. Calculer le centroïde **du polygone de zone**, pas du pays, pour les zones splittées.
10. **Charge perf carte** : deck.gl GPU ok, mais limiter le nb d'arcs visibles (filtrer |MW| < seuil), throttler les updates live.
11. **Cohérence Sankey/positions nettes** : la somme des flux doit réconcilier les positions nettes par zone — ajouter un test.

---

## 9. `CLAUDE.md` à coller dans le repo

Voir le fichier `CLAUDE.md` à la racine du repo (déjà en place).

**Comment piloter Claude Code** : ouvrir le repo, déposer `PLAN.md` + `CLAUDE.md`, puis lancer jalon par jalon — *« Implémente M0 selon PLAN.md, montre-moi le résultat, attends ma validation »*, etc. Laisser Claude Code écrire les fichiers `data/*.json` en interrogeant `entsoe-py` (ne pas les remplir à la main). Vérifier à chaque jalon le DoD correspondant.

---

## 10. Definition of Done (global)

- [ ] `docker compose up` → app complète, **zéro config**, en mode Energy-Charts (démo) ; bascule ENTSO-E si token.
- [ ] Carte live : zones colorées par prix réel + arcs animés cohérents + toggle commercial/physique + scrubber 48 h fluide + prix négatifs distincts.
- [ ] Congestion : heatmap spreads + leaderboard + indice de convergence.
- [ ] Explorateur d'interconnexions + pages détail (flux phys/prog, NTC vs flux, duration, spread, rente).
- [ ] Dashboards zone (prix/charge/mix/position/voisins) + Sankey réconcilié.
- [ ] Analytics : duration curves, corrélations, export CSV.
- [ ] Codes EIC issus d'`entsoe-py` (pas de mémoire) ; UTC partout ; FBMC traité correctement.
- [ ] Tests verts (pytest + Vitest) ; README clair (setup, sources, token, architecture).
- [ ] Design sombre cohérent, daltonien-safe, états loading/error propres.

---

### Annexe — pourquoi ces choix

- **deck.gl `ArcLayer`** : seule voie propre pour des arcs directionnels animés performants sur fond carto → c'est *le* différenciant visuel d'une app d'interconnexions.
- **Energy-Charts par défaut** : enlève le mur des ~3 jours d'attente token ENTSO-E → l'app tourne immédiatement, ENTSO-E vient en upgrade autoritaire.
- **DuckDB** : analytics time-series locales rapides sans serveur DB → idéal pour duration curves/corrélations/agrégats.
- **`entsoe-py` comme référentiel** : élimine le risque n°1 (codes EIC/adjacences faux) en s'appuyant sur un mapping maintenu.
