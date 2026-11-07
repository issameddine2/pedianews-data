"""Maps a German city to its KV region (Land; Nordrhein-Westfalen split into Nordrhein / Westfalen-Lippe).
Deterministic on purpose: the AI never decides the region. Unknown or online -> None (shown for every region)."""
import re

CITIES = {
    "Bayern": "München Nürnberg Nuernberg Augsburg Regensburg Würzburg Wuerzburg Erlangen Ingolstadt Fürth Bamberg Bayreuth Passau Landshut Rosenheim Coburg Kempten Memmingen Aschaffenburg Schweinfurt Straubing Garmisch Bad Reichenhall Murnau Starnberg",
    "Baden-Württemberg": "Stuttgart Karlsruhe Mannheim Freiburg Heidelberg Ulm Heilbronn Tübingen Tuebingen Konstanz Pforzheim Reutlingen Ludwigsburg Esslingen Baden-Baden Friedrichshafen Villingen Offenburg Ravensburg",
    "Berlin": "Berlin",
    "Brandenburg": "Potsdam Cottbus Brandenburg Frankfurt (Oder) Eberswalde Neuruppin Bad Saarow",
    "Bremen": "Bremen Bremerhaven",
    "Hamburg": "Hamburg",
    "Hessen": "Frankfurt Wiesbaden Kassel Darmstadt Offenbach Gießen Giessen Marburg Fulda Hanau Bad Homburg Bad Nauheim Rüsselsheim",
    "Mecklenburg-Vorpommern": "Rostock Schwerin Greifswald Neubrandenburg Stralsund Wismar Rügen Usedom",
    "Niedersachsen": "Hannover Göttingen Goettingen Braunschweig Oldenburg Osnabrück Osnabrueck Wolfsburg Hildesheim Lüneburg Celle Delmenhorst Salzgitter Wilhelmshaven Cuxhaven Goslar",
    "Nordrhein": "Köln Koeln Düsseldorf Duesseldorf Essen Duisburg Bonn Aachen Wuppertal Bochum Leverkusen Krefeld Mönchengladbach Neuss Oberhausen Solingen Remscheid Mülheim Siegburg",
    "Westfalen-Lippe": "Dortmund Münster Muenster Bielefeld Gelsenkirchen Paderborn Hagen Hamm Herne Bottrop Detmold Gütersloh Siegen Recklinghausen Lippstadt Minden Iserlohn Witten Bad Oeynhausen",
    "Rheinland-Pfalz": "Mainz Koblenz Trier Ludwigshafen Kaiserslautern Worms Speyer Landau Neustadt",
    "Saarland": "Saarbrücken Saarbruecken Homburg Neunkirchen Saarlouis",
    "Sachsen": "Dresden Leipzig Chemnitz Zwickau Plauen Görlitz Goerlitz Bautzen Freiberg",
    "Sachsen-Anhalt": "Magdeburg Halle Dessau Wittenberg Stendal Halberstadt",
    "Schleswig-Holstein": "Kiel Lübeck Luebeck Flensburg Neumünster Pelzerhaken Timmendorfer Husum Sylt Travemünde Eutin Plön Lübeck",
    "Thüringen": "Erfurt Jena Weimar Gera Eisenach Gotha Suhl Nordhausen Ilmenau",
}

_PATTERNS = []
for land, names in CITIES.items():
    # multi-word names are separated by single spaces in the strings above; split on known multiword stems
    toks = re.findall(r"Frankfurt \(Oder\)|Bad [A-ZÄÖÜ][\w-]+(?: [A-ZÄÖÜ]\w+)?|[\wÄÖÜäöüß-]+", names)
    for t in toks:
        _PATTERNS.append((t.lower(), land))
# longest names first so "Frankfurt (Oder)" beats "Frankfurt", "Mülheim" etc.
_PATTERNS.sort(key=lambda p: -len(p[0]))


def state_for(city):
    c = (city or "").strip().lower()
    if not c or "online" in c:
        return None
    for name, land in _PATTERNS:
        if re.search(r"(?<![\wäöüß])" + re.escape(name) + r"(?![\wäöüß])", c):
            return land
    return None
