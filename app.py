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
        return "#0b6e3f"


def weighted_score(props, weights):
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


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def build_feature_list(gdf_4326, weights):
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
    geom = feature["geometry"]
    geom_type = geom["type"]
    coords = geom["coordinates"]

    if geom_type == "Polygon":
        outer_ring = coords[0]
        return [[lat, lon] for lon, lat in outer_ring]

    elif geom_type == "MultiPolygon":
        all_polygons = []
        for polygon in coords:
            outer_ring = polygon[0]
            all_polygons.append([[lat, lon] for lon, lat in outer_ring])
        return all_polygons

    return []

def feature_bounds(feature, default_bounds):
    if feature is None:
        return default_bounds

    geom = feature["geometry"]
    geom_type = geom["type"]
    coords = geom["coordinates"]

    lons = []
    lats = []

    if geom_type == "Polygon":
        for lon, lat in coords[0]:
            lons.append(lon)
            lats.append(lat)

    elif geom_type == "MultiPolygon":
        for polygon in coords:
            for lon, lat in polygon[0]:
                lons.append(lon)
                lats.append(lat)

    if not lons or not lats:
        return default_bounds

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    return [[min_lat, min_lon], [max_lat, max_lon]]

def feature_center_zoom(feature, default_center, default_zoom=11):
    if feature is None:
        return default_center, default_zoom

    geom = feature["geometry"]
    geom_type = geom["type"]
    coords = geom["coordinates"]

    lons = []
    lats = []

    if geom_type == "Polygon":
        for lon, lat in coords[0]:
            lons.append(lon)
            lats.append(lat)

    elif geom_type == "MultiPolygon":
        for polygon in coords:
            for lon, lat in polygon[0]:
                lons.append(lon)
                lats.append(lat)

    if not lons or not lats:
        return default_center, default_zoom

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    c_lat = (min_lat + max_lat) / 2
    c_lon = (min_lon + max_lon) / 2

    max_dim = max(max_lon - min_lon, max_lat - min_lat)

    if max_dim > 0.08:
        zoom = 12
    elif max_dim > 0.04:
        zoom = 13
    elif max_dim > 0.02:
        zoom = 14
    elif max_dim > 0.01:
        zoom = 15
    else:
        zoom = 16

    return [c_lat, c_lon], zoom


def build_map_layers(features, selected_os_id=None):
    layers = []
    total_count = len(features)

    for i, feature in enumerate(features):
        props = feature["properties"]
        os_id = props["os_id"]
        os_name = props["os_name"]
        score = props["dynamic_score_final"]
        color = props["dynamic_color"]
        
        rank = i + 1

        positions = polygon_positions_from_feature(feature)

        polygon = dl.Polygon(
            positions=positions,
            pathOptions={
                "fillColor": color,
                "fillOpacity": 0.8,
                "color": "#d1d5db",
                "weight": 1.2,
                "opacity": 1.0,
            },
            children=[
                dl.Tooltip(f"{os_name} | Wynik: {score:.2f}"),
                dl.Popup(
                    details_card(feature, rank=rank, total_count=total_count),
                    maxWidth=350,
                ),
            ],
        )
        layers.append(polygon)

    return layers


def build_top_list(features, selected_os_id=None, top_n=10):
    items = []
    medals = ["🥇", "🥈", "🥉"]

    for i, feature in enumerate(features[:top_n]):
        props = feature["properties"]
        os_id = str(props["os_id"])
        prefix = medals[i] if i < 3 else f"{i+1}."
        is_selected = str(selected_os_id) == os_id

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
                id={"type": "top-item", "index": os_id},
                action=True,
                active=is_selected,
                color="success" if i == 0 and not is_selected else None,
            )
        )

    return items


def find_feature_by_os_id(features, os_id):
    for feature in features:
        if str(feature["properties"]["os_id"]) == str(os_id):
            return feature
    return None


def find_rank_by_os_id(features, os_id):
    for i, feature in enumerate(features, start=1):
        if str(feature["properties"]["os_id"]) == str(os_id):
            return i
    return None


def details_card(feature, rank=None, total_count=None):
    if feature is None:
        return dbc.Card(
            dbc.CardBody(
                [
                    html.H5("Szczegóły osiedla", className="card-title"),
                    html.P(
                        "Kliknij osiedle na mapie albo w rankingu, aby zobaczyć szczegóły.",
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
                    className="mb-2",
                ),
                html.P(
                    f"Pozycja w rankingu: {rank} / {total_count}" if rank is not None else "",
                    className="text-muted mb-3",
                ),
                html.Hr(),
                html.P(f"Zieleń i rekreacja: {p['score_green']:.2f}/100", className="mb-1"),
                html.P(f"Komunikacja miejska: {p['score_transport']:.2f}/100", className="mb-1"),
                html.P(f"Edukacja: {p['score_education']:.2f}/100", className="mb-1"),
                html.P(f"Rozrywka i gastronomia: {p['score_food']:.2f}/100", className="mb-1"),
                html.P(f"Spokój / brak hałasu: {p['score_peace']:.2f}/100", className="mb-3"),
                html.Hr(),
                html.H6("Dane źródłowe", className="mb-2"),
                html.P(f"Parki w 2 km: {safe_int(p.get('park_count_2km'))}", className="mb-1"),
                html.P(f"Szkoły w 2 km: {safe_int(p.get('school_count_2km'))}", className="mb-1"),
                html.P(f"Przystanki w 800 m: {safe_int(p.get('stop_count_800m'))}", className="mb-1"),
                html.P(f"Restauracje w 1.5 km: {safe_int(p.get('food_count_1500m'))}", className="mb-1"),
                html.P(
                    f"Udział zieleni: {round(safe_float(p.get('green_share')) * 100, 2)}%",
                    className="mb-1"
                ),
                html.P(
                    f"Długość dróg głównych: {round(safe_float(p.get('road_length_m')), 1)} m",
                    className="mb-0"
                ),
            ]
        ),
        className="border-0 shadow-sm",
    )


# ============================================================
# WCZYTANIE DANYCH
# ============================================================

gdf = gpd.read_file(GEOJSON_PATH)

if gdf.crs is None:
    raise ValueError("Warstwa osiedla_wyniki.geojson nie ma CRS.")

gdf_4326 = gdf.to_crs(epsg=4326)

bounds = gdf_4326.total_bounds  # minx, miny, maxx, maxy
center_lat = (bounds[1] + bounds[3]) / 2
center_lon = (bounds[0] + bounds[2]) / 2
default_map_center = [center_lat, center_lon]
default_map_zoom = 11
default_map_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]


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

        html.Label(id="label-green", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["green"],
            id="slider-green",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        html.Label(id="label-transport", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["transport"],
            id="slider-transport",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        html.Label(id="label-education", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["education"],
            id="slider-education",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        html.Label(id="label-food", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["food"],
            id="slider-food",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        html.Label(id="label-peace", className="fw-semibold"),
        dcc.Slider(
            0, 100, 10,
            value=DEFAULT_WEIGHTS["peace"],
            id="slider-peace",
            marks={i: str(i) for i in range(0, 101, 20)},
            tooltip={"placement": "bottom"},
        ),
        html.Br(),

        dbc.Button(
            "Oblicz",
            id="btn-calculate",
            color="primary",
            className="w-100 shadow-sm mb-2",
            n_clicks=0,
        ),

        dbc.Button(
            "Reset wag",
            id="btn-reset",
            color="secondary",
            className="w-100 shadow-sm mb-3",
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
                                    "backgroundColor": "#0b6e3f",
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
                            "Interaktywna mapa atrakcyjności zamieszkania oparta na rzeczywistych sektorach i wskaźnikach przestrzennych.",
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
                                                        bounds=default_map_bounds,
                                                        boundsOptions={"padding": [50, 50]},
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
                                        dbc.Card(
                                            dbc.CardBody(
                                                [
                                                    html.H4("Top 10", className="text-success mb-3"),
                                                    dbc.ListGroup(id="top-list")
                                                ]
                                            ),
                                            className="border-0 shadow-sm",
                                            style={"height": MAP_HEIGHT, "overflowY": "auto"}
                                        ),
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
    Output("slider-green", "value"),
    Output("slider-transport", "value"),
    Output("slider-education", "value"),
    Output("slider-food", "value"),
    Output("slider-peace", "value"),
    Input("btn-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_sliders(n_clicks):
    return (
        DEFAULT_WEIGHTS["green"],
        DEFAULT_WEIGHTS["transport"],
        DEFAULT_WEIGHTS["education"],
        DEFAULT_WEIGHTS["food"],
        DEFAULT_WEIGHTS["peace"],
    )


@app.callback(
    Output("weights-store", "data"),
    Input("btn-calculate", "n_clicks"),
    Input("btn-reset", "n_clicks"),
    State("slider-green", "value"),
    State("slider-transport", "value"),
    State("slider-education", "value"),
    State("slider-food", "value"),
    State("slider-peace", "value"),
)
def update_weights_store(calc_clicks, reset_clicks, green, transport, education, food, peace):
    if ctx.triggered_id == "btn-reset":
        return {
            "green": DEFAULT_WEIGHTS["green"],
            "transport": DEFAULT_WEIGHTS["transport"],
            "education": DEFAULT_WEIGHTS["education"],
            "food": DEFAULT_WEIGHTS["food"],
            "peace": DEFAULT_WEIGHTS["peace"],
        }
        
    return {
        "green": green,
        "transport": transport,
        "education": education,
        "food": food,
        "peace": peace,
    }


@app.callback(
    Output("label-green", "children"),
    Output("label-transport", "children"),
    Output("label-education", "children"),
    Output("label-food", "children"),
    Output("label-peace", "children"),
    Input("slider-green", "value"),
    Input("slider-transport", "value"),
    Input("slider-education", "value"),
    Input("slider-food", "value"),
    Input("slider-peace", "value"),
)
def update_slider_labels(green, transport, education, food, peace):
    return (
        f"Zieleń i rekreacja ({green})",
        f"Komunikacja miejska ({transport})",
        f"Edukacja ({education})",
        f"Rozrywka i gastronomia ({food})",
        f"Spokój / brak hałasu ({peace})",
    )


@app.callback(
    Output("selected-os-id", "data"),
    Input({"type": "top-item", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def update_selected_osiedle(top_clicks):
    if not ctx.triggered_id:
        return dash.no_update
    return ctx.triggered_id.get("index")


@app.callback(
    Output("osiedla-layer", "children"),
    Output("top-list", "children"),
    Input("weights-store", "data"),
)
def update_map_and_panels(weights):
    features = build_feature_list(gdf_4326, weights)
    layers = build_map_layers(features)
    top_items = build_top_list(features, top_n=10)

    return layers, top_items


@app.callback(
    Output("map", "viewport"),
    Input("selected-os-id", "data"),
    State("weights-store", "data"),
    prevent_initial_call=True,
)
def update_map_view(selected_os_id, weights):
    if not selected_os_id:
        return dash.no_update

    features = build_feature_list(gdf_4326, weights)
    selected_feature = find_feature_by_os_id(features, selected_os_id)

    b = feature_bounds(
        selected_feature,
        default_bounds=default_map_bounds,
    )
    
    center_lat = (b[0][0] + b[1][0]) / 2.0
    center_lon = (b[0][1] + b[1][1]) / 2.0

    return dict(center=[center_lat, center_lon], zoom=15, transition="flyTo")

# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)