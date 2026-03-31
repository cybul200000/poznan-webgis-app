import geopandas as gpd
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, ALL, ctx
import dash_leaflet as dl
from pathlib import Path

# ============================================================
# KONFIGURACJA
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
GEOJSON_PATH = BASE_DIR / "data" / "osiedla_wyniki.geojson"

DEFAULT_WEIGHTS = {
    "green": 80,
    "transport": 70,
    "education": 50,
    "food": 40,
    "peace": 60,
}

MAP_HEIGHT = "72vh"


# ============================================================
# FUNKCJE POMOCNICZE
# ============================================================

def score_to_color(score):
    """
    Skala kolorów: czerwony -> żółty -> zielony
    """
    if score < 20:
        return "#a50026"
    elif score < 35:
        return "#d73027"
    elif score < 50:
        return "#f46d43"
    elif score < 65:
        return "#fee08b"
    elif score < 80:
        return "#a6d96a"
    else:
        return "#1a9850"


def weighted_score(props, weights):
    """
    Liczy wynik końcowy z już wyliczonych wskaźników cząstkowych:
    - score_green
    - score_transport
    - score_education
    - score_food
    - score_peace
    """
    total_weight = sum(weights.values())
    if total_weight == 0:
        return round(
            (
                props["score_green"]
                + props["score_transport"]
                + props["score_education"]
                + props["score_food"]
                + props["score_peace"]
            ) / 5.0,
            2,
        )

    score = (
        props["score_green"] * weights["green"]
        + props["score_transport"] * weights["transport"]
        + props["score_education"] * weights["education"]
        + props["score_food"] * weights["food"]
        + props["score_peace"] * weights["peace"]
    ) / total_weight

    return round(score, 2)


def build_feature_list(gdf_4326, weights):
    """
    Tworzy listę obiektów z nowym wynikiem końcowym liczonym
    dynamicznie wg aktualnych wag.
    """
    features = []
    for _, row in gdf_4326.iterrows():
        props = row.drop(labels="geometry").to_dict()

        score = weighted_score(props, weights)
        props["dynamic_score_final"] = score
        props["dynamic_color"] = score_to_color(score)

        feature = {
            "type": "Feature",
            "geometry": row.geometry.__geo_interface__,
            "properties": props,
        }
        features.append(feature)

    features.sort(
        key=lambda f: f["properties"]["dynamic_score_final"],
        reverse=True
    )
    return features


def polygon_positions_from_feature(feature):
    """
    Zamienia geometrię GeoJSON Polygon na format positions dla dash-leaflet.
    GeoJSON ma [lon, lat], a dash-leaflet chce [lat, lon].
    """
    coords = feature["geometry"]["coordinates"]

    # Polygon -> bierzemy tylko zewnętrzny pierścień
    outer_ring = coords[0]
    positions = [[lat, lon] for lon, lat in outer_ring]
    return positions


def build_map_layers(features, selected_os_id=None):
    """
    Buduje polygon layers dla mapy.
    """
    layers = []

    for feature in features:
        props = feature["properties"]
        os_id = props["os_id"]
        os_name = props["os_name"]
        score = props["dynamic_score_final"]
        color = props["dynamic_color"]

        is_selected = (selected_os_id == os_id)

        polygon = dl.Polygon(
            id={"type": "osiedle-polygon", "index": str(os_id)},
            positions=polygon_positions_from_feature(feature),
            pathOptions={
                "fillColor": color,
                "fillOpacity": 0.65,
                "color": "#1f2937" if is_selected else "#ffffff",
                "weight": 4 if is_selected else 1.8,
                "opacity": 1.0,
            },
            children=[
                dl.Tooltip(f"{os_name} | Wynik: {score:.2f}"),
                dl.Popup(
                    html.Div(
                        [
                            html.H6(os_name, className="mb-2"),
                            html.P(f"Wynik końcowy: {score:.2f}/100", className="mb-1"),
                            html.Small("Kliknij obszar, aby odświeżyć panel szczegółów."),
                        ]
                    )
                ),
            ],
        )
        layers.append(polygon)

    return layers


def build_top_list(features, top_n=10):
    items = []
    medals = ["🥇", "🥈", "🥉"]

    for i, feature in enumerate(features[:top_n]):
        props = feature["properties"]
        prefix = medals[i] if i < 3 else f"{i+1}."
        color = "success" if i == 0 else "light"

        items.append(
            dbc.ListGroupItem(
                [
                    html.Span(f"{prefix} ", className="fw-bold"),
                    html.Span(props["os_name"]),
                    html.Span(
                        f" (Wynik: {props['dynamic_score_final']:.2f})",
                        className="fw-bold"
                    ),
                ],
                color=color,
            )
        )
    return items


def find_feature_by_os_id(features, os_id):
    for feature in features:
        if str(feature["properties"]["os_id"]) == str(os_id):
            return feature
    return None


def details_card(feature):
    if feature is None:
        return dbc.Card(
            dbc.CardBody(
                [
                    html.H5("Szczegóły osiedla", className="card-title"),
                    html.P(
                        "Kliknij osiedle na mapie, aby zobaczyć szczegóły.",
                        className="text-muted mb-0",
                    ),
                ]
            ),
            className="border-0 shadow-sm",
        )

    p = feature["properties"]

    return dbc.Card(
        dbc.CardBody(
            [
                html.H4(p["os_name"], className="card-title mb-3"),
                html.Div(
                    [
                        html.Span("Wynik końcowy: ", className="fw-bold"),
                        html.Span(
                            f"{p['dynamic_score_final']:.2f}/100",
                            style={
                                "color": p["dynamic_color"],
                                "fontWeight": "700",
                                "fontSize": "1.25rem",
                            },
                        ),
                    ],
                    className="mb-3",
                ),
                html.Hr(),
                html.P(f"Zieleń i rekreacja: {p['score_green']:.2f}/100", className="mb-1"),
                html.P(f"Komunikacja miejska: {p['score_transport']:.2f}/100", className="mb-1"),
                html.P(f"Edukacja: {p['score_education']:.2f}/100", className="mb-1"),
                html.P(f"Rozrywka i gastronomia: {p['score_food']:.2f}/100", className="mb-1"),
                html.P(f"Spokój / brak hałasu: {p['score_peace']:.2f}/100", className="mb-3"),

                html.Hr(),
                html.H6("Dane źródłowe", className="mb-2"),
                html.P(f"Parki w 2 km: {int(p['park_count_2km'])}", className="mb-1"),
                html.P(f"Szkoły w 2 km: {int(p['school_count_2km'])}", className="mb-1"),
                html.P(f"Przystanki w 800 m: {int(p['stop_count_800m'])}", className="mb-1"),
                html.P(f"Restauracje w 1.5 km: {int(p['food_count_1500m'])}", className="mb-1"),
                html.P(f"Udział zieleni: {round(float(p['green_share']) * 100, 2)}%", className="mb-1"),
                html.P(f"Długość dróg głównych: {round(float(p['road_length_m']), 1)} m", className="mb-0"),
            ]
        ),
        className="border-0 shadow-sm",
    )


# ============================================================
# WCZYTANIE DANYCH
# ============================================================

gdf = gpd.read_file(GEOJSON_PATH)

# GeoJSON masz w EPSG:2180, więc do mapy trzeba przeliczyć na 4326
if gdf.crs is None:
    raise ValueError("Warstwa osiedla_wyniki.geojson nie ma CRS.")
gdf_4326 = gdf.to_crs(epsg=4326)

bounds = gdf_4326.total_bounds  # minx, miny, maxx, maxy
center_lat = (bounds[1] + bounds[3]) / 2
center_lon = (bounds[0] + bounds[2]) / 2

initial_features = build_feature_list(gdf_4326, DEFAULT_WEIGHTS)


# ============================================================
# APLIKACJA
# ============================================================

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
server = app.server
app.title = "Atrakcyjność zamieszkania - Poznań"

sidebar = html.Div(
    [
        html.H2("Kryteria", className="mb-3"),
        html.Hr(),
        html.P("Ustaw wagi dla poszczególnych wskaźników:", className="text-muted"),

        html.Label("Zieleń i rekreacja", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["green"],
            id="slider-green",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        html.Label("Komunikacja miejska", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["transport"],
            id="slider-transport",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        html.Label("Edukacja", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["education"],
            id="slider-education",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        html.Label("Rozrywka i gastronomia", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["food"],
            id="slider-food",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        html.Label("Spokój / brak hałasu", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["peace"],
            id="slider-peace",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        dbc.Button(
            "Przelicz ranking",
            id="btn-recalculate",
            color="primary",
            className="w-100 shadow-sm",
            n_clicks=0,
        ),

        html.Hr(),

        dbc.Card(
            dbc.CardBody(
                [
                    html.H6("Legenda", className="mb-3"),
                    html.Div(
                        [
                            html.Span(
                                style={
                                    "display": "inline-block",
                                    "width": "18px",
                                    "height": "18px",
                                    "backgroundColor": "#d73027",
                                    "marginRight": "8px",
                                    "borderRadius": "3px",
                                }
                            ),
                            html.Span("niski wynik"),
                        ],
                        className="mb-2",
                    ),
                    html.Div(
                        [
                            html.Span(
                                style={
                                    "display": "inline-block",
                                    "width": "18px",
                                    "height": "18px",
                                    "backgroundColor": "#fee08b",
                                    "marginRight": "8px",
                                    "borderRadius": "3px",
                                }
                            ),
                            html.Span("średni wynik"),
                        ],
                        className="mb-2",
                    ),
                    html.Div(
                        [
                            html.Span(
                                style={
                                    "display": "inline-block",
                                    "width": "18px",
                                    "height": "18px",
                                    "backgroundColor": "#1a9850",
                                    "marginRight": "8px",
                                    "borderRadius": "3px",
                                }
                            ),
                            html.Span("wysoki wynik"),
                        ],
                    ),
                ]
            ),
            className="border-0 shadow-sm",
        ),
    ],
    style={
        "padding": "2rem",
        "backgroundColor": "#f8f9fa",
        "minHeight": "100vh",
        "borderRight": "1px solid #e9ecef",
    },
)

app.layout = dbc.Container(
    [
        dcc.Store(id="weights-store", data=DEFAULT_WEIGHTS),
        dcc.Store(id="selected-os-id", data=None),

        dbc.Row(
            [
                dbc.Col(sidebar, md=4, lg=3),

                dbc.Col(
                    [
                        html.H2("Wybór idealnego miejsca do życia - Poznań", className="mt-4 mb-2"),
                        html.P(
                            "Interaktywna mapa atrakcyjności zamieszkania oparta na rzeczywistych osiedlach i wskaźnikach przestrzennych.",
                            className="text-muted mb-4",
                        ),

                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        dbc.Card(
                                            dbc.CardBody(
                                                [
                                                    dl.Map(
                                                        id="map",
                                                        center=[center_lat, center_lon],
                                                        zoom=11,
                                                        children=[
                                                            dl.TileLayer(),
                                                            dl.LayerGroup(id="osiedla-layer"),
                                                        ],
                                                        style={
                                                            "width": "100%",
                                                            "height": MAP_HEIGHT,
                                                            "borderRadius": "16px",
                                                        },
                                                    )
                                                ]
                                            ),
                                            className="border-0 shadow-sm",
                                        )
                                    ],
                                    lg=8,
                                ),

                                dbc.Col(
                                    [
                                        html.Div(id="details-panel", className="mb-3"),
                                        dbc.Card(
                                            dbc.CardBody(
                                                [
                                                    html.H4("Top 10 osiedli", className="text-success mb-3"),
                                                    dbc.ListGroup(id="top-list")
                                                ]
                                            ),
                                            className="border-0 shadow-sm",
                                        )
                                    ],
                                    lg=4,
                                ),
                            ],
                            className="g-3",
                        ),
                    ],
                    md=8,
                    lg=9,
                    style={"padding": "1.5rem 2rem"},
                ),
            ],
            className="g-0",
        ),
    ],
    fluid=True,
)


# ============================================================
# CALLBACKS
# ============================================================

@app.callback(
    Output("weights-store", "data"),
    Input("btn-recalculate", "n_clicks"),
    State("slider-green", "value"),
    State("slider-transport", "value"),
    State("slider-education", "value"),
    State("slider-food", "value"),
    State("slider-peace", "value"),
    prevent_initial_call=False,
)
def update_weights_store(n_clicks, green, transport, education, food, peace):
    return {
        "green": green,
        "transport": transport,
        "education": education,
        "food": food,
        "peace": peace,
    }


@app.callback(
    Output("selected-os-id", "data"),
    Input({"type": "osiedle-polygon", "index": ALL}, "n_clicks"),
    State("selected-os-id", "data"),
    prevent_initial_call=True,
)
def update_selected_osiedle(n_clicks_list, current_selected):
    if not ctx.triggered_id:
        return current_selected

    triggered = ctx.triggered_id
    if isinstance(triggered, dict) and triggered.get("type") == "osiedle-polygon":
        return triggered.get("index")

    return current_selected


@app.callback(
    Output("osiedla-layer", "children"),
    Output("top-list", "children"),
    Output("details-panel", "children"),
    Input("weights-store", "data"),
    Input("selected-os-id", "data"),
)
def update_map_and_panels(weights, selected_os_id):
    features = build_feature_list(gdf_4326, weights)

    if selected_os_id is None and features:
        selected_os_id = str(features[0]["properties"]["os_id"])

    selected_feature = find_feature_by_os_id(features, selected_os_id)

    layers = build_map_layers(features, selected_os_id=selected_os_id)
    top_items = build_top_list(features, top_n=10)
    details = details_card(selected_feature)

    return layers, top_items, details


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)