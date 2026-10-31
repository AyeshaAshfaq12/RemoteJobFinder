"""Countries, regions, and cities used by eligibility and title normalization.

DRAFT for human review (decided 2026-10-29): regions follow UN M49 where one exists, and the
usual hiring meaning otherwise. Pakistan (PK) is IN: asia, apac, south_asia.
PK is NOT in: emea, mena, middle_east, europe. Cyprus is counted as Europe (EU member).
"""

import re
from functools import lru_cache

# ISO 3166-1 alpha-2 -> English short name (+ common aliases after the "|").
_COUNTRIES_RAW = """
AF Afghanistan
AL Albania
DZ Algeria
AD Andorra
AO Angola
AG Antigua and Barbuda
AR Argentina
AM Armenia
AU Australia
AT Austria
AZ Azerbaijan
BS Bahamas
BH Bahrain
BD Bangladesh
BB Barbados
BY Belarus
BE Belgium
BZ Belize
BJ Benin
BT Bhutan
BO Bolivia
BA Bosnia and Herzegovina|Bosnia
BW Botswana
BR Brazil|Brasil
BN Brunei
BG Bulgaria
BF Burkina Faso
BI Burundi
CV Cape Verde|Cabo Verde
KH Cambodia
CM Cameroon
CA Canada
CF Central African Republic
TD Chad
CL Chile
CN China
CO Colombia
KM Comoros
CG Congo|Republic of the Congo
CD Democratic Republic of the Congo|DR Congo|DRC
CR Costa Rica
CI Ivory Coast|Cote d'Ivoire|Côte d'Ivoire
HR Croatia
CU Cuba
CY Cyprus
CZ Czech Republic|Czechia
DK Denmark
DJ Djibouti
DM Dominica
DO Dominican Republic
EC Ecuador
EG Egypt
SV El Salvador
GQ Equatorial Guinea
ER Eritrea
EE Estonia
SZ Eswatini|Swaziland
ET Ethiopia
FJ Fiji
FI Finland
FR France
GA Gabon
GM Gambia
GE Georgia
DE Germany|Deutschland
GH Ghana
GR Greece
GD Grenada
GT Guatemala
GN Guinea
GW Guinea-Bissau
GY Guyana
HT Haiti
HN Honduras
HK Hong Kong
HU Hungary
IS Iceland
IN India
ID Indonesia
IR Iran
IQ Iraq
IE Ireland
IL Israel
IT Italy
JM Jamaica
JP Japan
JO Jordan
KZ Kazakhstan
KE Kenya
KI Kiribati
XK Kosovo
KW Kuwait
KG Kyrgyzstan
LA Laos
LV Latvia
LB Lebanon
LS Lesotho
LR Liberia
LY Libya
LI Liechtenstein
LT Lithuania
LU Luxembourg
MO Macau|Macao
MG Madagascar
MW Malawi
MY Malaysia
MV Maldives
ML Mali
MT Malta
MH Marshall Islands
MR Mauritania
MU Mauritius
MX Mexico
FM Micronesia
MD Moldova
MC Monaco
MN Mongolia
ME Montenegro
MA Morocco
MZ Mozambique
MM Myanmar|Burma
NA Namibia
NR Nauru
NP Nepal
NL Netherlands|Holland|The Netherlands
NZ New Zealand
NI Nicaragua
NE Niger
NG Nigeria
KP North Korea
MK North Macedonia|Macedonia
NO Norway
OM Oman
PK Pakistan
PW Palau
PS Palestine
PA Panama
PG Papua New Guinea
PY Paraguay
PE Peru
PH Philippines
PL Poland
PT Portugal
PR Puerto Rico
QA Qatar
RO Romania
RU Russia|Russian Federation
RW Rwanda
KN Saint Kitts and Nevis
LC Saint Lucia
VC Saint Vincent and the Grenadines
WS Samoa
SM San Marino
ST Sao Tome and Principe
SA Saudi Arabia|KSA
SN Senegal
RS Serbia
SC Seychelles
SL Sierra Leone
SG Singapore
SK Slovakia
SI Slovenia
SB Solomon Islands
SO Somalia
ZA South Africa
KR South Korea|Korea
SS South Sudan
ES Spain|España
LK Sri Lanka
SD Sudan
SR Suriname
SE Sweden
CH Switzerland
SY Syria
TW Taiwan
TJ Tajikistan
TZ Tanzania
TH Thailand
TL Timor-Leste|East Timor
TG Togo
TO Tonga
TT Trinidad and Tobago
TN Tunisia
TR Turkey|Türkiye|Turkiye
TM Turkmenistan
TV Tuvalu
UG Uganda
UA Ukraine
AE United Arab Emirates|UAE|Dubai|Abu Dhabi
GB United Kingdom|UK|U.K.|Great Britain|Britain|England|Scotland|Wales|Northern Ireland
US United States|United States of America|USA|U.S.A.|US|U.S.|America
UY Uruguay
UZ Uzbekistan
VU Vanuatu
VA Vatican City
VE Venezuela
VN Vietnam|Viet Nam
YE Yemen
ZM Zambia
ZW Zimbabwe
"""


def _parse_countries() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in _COUNTRIES_RAW.strip().splitlines():
        code, names = line.split(" ", 1)
        out[code] = names.split("|")
    return out


COUNTRY_NAMES: dict[str, list[str]] = _parse_countries()
ALL_COUNTRIES: frozenset[str] = frozenset(COUNTRY_NAMES)

# Names/aliases that are only matched when written in upper case in the source text,
# because their lower-case forms are ordinary words or ambiguous ("us", "korea").
_CASE_SENSITIVE_ALIASES = {"US", "U.S.", "UK", "U.K.", "UAE", "KSA", "DRC", "USA", "U.S.A."}

# --- Regions --------------------------------------------------------------------------------

EU = frozenset(
    [
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
    ]
)
EEA = EU | {"IS", "LI", "NO"}
EUROPE = EU | frozenset(
    [
        "AL",
        "AD",
        "BY",
        "BA",
        "XK",
        "LI",
        "IS",
        "MD",
        "MC",
        "ME",
        "MK",
        "NO",
        "RU",
        "SM",
        "RS",
        "CH",
        "UA",
        "GB",
        "VA",
    ]
)
AFRICA = frozenset(
    [
        "DZ",
        "AO",
        "BJ",
        "BW",
        "BF",
        "BI",
        "CV",
        "CM",
        "CF",
        "TD",
        "KM",
        "CG",
        "CD",
        "CI",
        "DJ",
        "EG",
        "GQ",
        "ER",
        "SZ",
        "ET",
        "GA",
        "GM",
        "GH",
        "GN",
        "GW",
        "KE",
        "LS",
        "LR",
        "LY",
        "MG",
        "MW",
        "ML",
        "MR",
        "MU",
        "MA",
        "MZ",
        "NA",
        "NE",
        "NG",
        "RW",
        "ST",
        "SN",
        "SC",
        "SL",
        "SO",
        "ZA",
        "SS",
        "SD",
        "TZ",
        "TG",
        "TN",
        "UG",
        "ZM",
        "ZW",
    ]
)
MIDDLE_EAST = frozenset(
    [
        "AE",
        "BH",
        "CY",
        "EG",
        "IL",
        "IQ",
        "IR",
        "JO",
        "KW",
        "LB",
        "OM",
        "PS",
        "QA",
        "SA",
        "SY",
        "TR",
        "YE",
    ]
)
NORTH_AFRICA = frozenset(["DZ", "EG", "LY", "MA", "TN"])
MENA = frozenset(
    [
        "DZ",
        "BH",
        "DJ",
        "EG",
        "IR",
        "IQ",
        "IL",
        "JO",
        "KW",
        "LB",
        "LY",
        "MA",
        "OM",
        "PS",
        "QA",
        "SA",
        "SY",
        "TN",
        "AE",
        "YE",
    ]
)
GCC = frozenset(["AE", "BH", "KW", "OM", "QA", "SA"])
CENTRAL_ASIA = frozenset(["KZ", "KG", "TJ", "TM", "UZ"])
EAST_ASIA = frozenset(["CN", "HK", "MO", "JP", "KP", "KR", "MN", "TW"])
SOUTHEAST_ASIA = frozenset(["BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN"])
SOUTH_ASIA = frozenset(["AF", "BD", "BT", "IN", "IR", "MV", "NP", "PK", "LK"])
WESTERN_ASIA = frozenset(
    [
        "AM",
        "AZ",
        "BH",
        "CY",
        "GE",
        "IQ",
        "IL",
        "JO",
        "KW",
        "LB",
        "OM",
        "QA",
        "SA",
        "PS",
        "SY",
        "TR",
        "AE",
        "YE",
    ]
)
ASIA = CENTRAL_ASIA | EAST_ASIA | SOUTHEAST_ASIA | SOUTH_ASIA | WESTERN_ASIA
OCEANIA = frozenset(
    ["AU", "NZ", "FJ", "PG", "SB", "VU", "WS", "TO", "KI", "FM", "MH", "PW", "NR", "TV"]
)
APAC = EAST_ASIA | SOUTHEAST_ASIA | SOUTH_ASIA | OCEANIA
EMEA = EUROPE | MIDDLE_EAST | AFRICA
NORTH_AMERICA = frozenset({"US", "CA"})
LATAM = frozenset(
    [
        "MX",
        "BZ",
        "CR",
        "SV",
        "GT",
        "HN",
        "NI",
        "PA",
        "AR",
        "BO",
        "BR",
        "CL",
        "CO",
        "EC",
        "GY",
        "PY",
        "PE",
        "SR",
        "UY",
        "VE",
        "CU",
        "DO",
        "HT",
        "PR",
        "JM",
        "TT",
        "BS",
        "BB",
    ]
)
AMERICAS = NORTH_AMERICA | LATAM
SOUTH_AMERICA = frozenset(["AR", "BO", "BR", "CL", "CO", "EC", "GY", "PY", "PE", "SR", "UY", "VE"])
CEE = frozenset(
    [
        "AL",
        "BA",
        "BG",
        "HR",
        "CZ",
        "EE",
        "HU",
        "XK",
        "LV",
        "LT",
        "MD",
        "ME",
        "MK",
        "PL",
        "RO",
        "RS",
        "SK",
        "SI",
        "UA",
    ]
)
DACH = frozenset({"DE", "AT", "CH"})
NORDICS = frozenset({"DK", "FI", "IS", "NO", "SE"})
BENELUX = frozenset({"BE", "NL", "LU"})
ANZ = frozenset({"AU", "NZ"})

# Region phrase (regex, lower-case) -> countries. Longest/most specific phrases first.
REGIONS: tuple[tuple[str, frozenset[str]], ...] = (
    (r"emea", EMEA),
    (r"apac|asia[- ]pacific|asia pac", APAC),
    (r"mena|middle east (?:and|&) north africa", MENA),
    (r"south america", SOUTH_AMERICA),
    (r"latam|latin america|central america", LATAM),
    (r"north america", NORTH_AMERICA),
    (r"americas", AMERICAS),
    (r"south[- ]?east asia|sea region", SOUTHEAST_ASIA),
    (r"south asia", SOUTH_ASIA),
    (r"east asia", EAST_ASIA),
    (r"central asia", CENTRAL_ASIA),
    (r"middle east", MIDDLE_EAST),
    (r"gcc|gulf", GCC),
    (r"north africa", NORTH_AFRICA),
    (r"africa", AFRICA),
    (r"eea", EEA),
    (r"european union|eu", EU),
    (r"cee|central (?:and|&) eastern europe|eastern europe", CEE),
    (r"europe|european", EUROPE),
    (r"dach", DACH),
    (r"nordics?|scandinavia", NORDICS),
    (r"benelux", BENELUX),
    (r"anz", ANZ),
    (r"oceania", OCEANIA),
    (r"asia", ASIA),
)
_REGION_PATTERNS = tuple((re.compile(rf"\b(?:{p})\b"), c) for p, c in REGIONS)

# Major cities that appear in remote-job location strings (lower-case).
CITIES = frozenset(
    """
    new york|nyc|san francisco|sf|bay area|los angeles|seattle|austin|boston|chicago|denver|
    atlanta|miami|washington dc|dc|portland|san diego|san jose|palo alto|mountain view|
    toronto|vancouver|montreal|ottawa|london|manchester|edinburgh|dublin|berlin|munich|
    hamburg|frankfurt|amsterdam|rotterdam|paris|lyon|madrid|barcelona|lisbon|porto|milan|
    rome|zurich|geneva|vienna|prague|warsaw|krakow|budapest|bucharest|sofia|belgrade|
    athens|stockholm|oslo|copenhagen|helsinki|tallinn|riga|vilnius|kyiv|kiev|istanbul|
    tel aviv|cairo|lagos|nairobi|cape town|johannesburg|karachi|lahore|islamabad|
    bangalore|bengaluru|mumbai|delhi|new delhi|hyderabad|pune|chennai|gurgaon|noida|
    dhaka|colombo|singapore|kuala lumpur|jakarta|manila|bangkok|ho chi minh city|hanoi|
    hong kong|shanghai|beijing|shenzhen|taipei|seoul|tokyo|sydney|melbourne|brisbane|
    auckland|mexico city|guadalajara|bogota|bogotá|medellin|medellín|sao paulo|são paulo|
    rio de janeiro|buenos aires|santiago|lima|montevideo|riyadh|jeddah|doha|amman|beirut
    """.replace("\n", "")
    .replace(" ", " ")
    .split("|")
)
_CITY_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(sorted((re.escape(c.strip()) for c in CITIES if c.strip()), key=len, reverse=True))
    + r")\b"
)
# "Austin, TX" style US state suffix.
_US_STATE = re.compile(
    r",\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|"
    r"NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b"
)
_REMOTE_WORDS = re.compile(r"\b(remote|anywhere|worldwide|global|distributed|wfh)\b")


@lru_cache(maxsize=1)
def _country_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    pats: list[tuple[re.Pattern[str], str]] = []
    for code, names in COUNTRY_NAMES.items():
        for name in names:
            flags = 0 if name in _CASE_SENSITIVE_ALIASES or name == "America" else re.IGNORECASE
            # "America" alone means the US only when capitalised and not part of a region name.
            prefix = r"(?<![A-Za-z.])"
            suffix = r"(?![A-Za-z])"
            if name == "America":
                prefix = r"(?<!North )(?<!South )(?<!Latin )(?<!Central )(?<![A-Za-z.])"
            pats.append((re.compile(prefix + re.escape(name) + suffix, flags), code))
    # Longest names first so "Democratic Republic of the Congo" wins over "Congo".
    pats.sort(key=lambda p: len(p[0].pattern), reverse=True)
    return tuple(pats)


def find_countries(text: str) -> set[str]:
    """ISO codes of countries named in text. Longer names consume their span first."""
    found: set[str] = set()
    remaining = text
    for pattern, code in _country_patterns():
        if pattern.search(remaining):
            found.add(code)
            remaining = pattern.sub(" ", remaining)
    return found


def find_regions(text: str) -> tuple[set[str], list[str]]:
    """Union of countries for region names in text, and the region phrases matched."""
    lowered = text.lower()
    countries: set[str] = set()
    matched: list[str] = []
    for pattern, codes in _REGION_PATTERNS:
        m = pattern.search(lowered)
        if m:
            countries |= codes
            matched.append(m.group(0))
            lowered = pattern.sub(" ", lowered)
    return countries, matched


def has_city(text: str) -> bool:
    return bool(_CITY_PATTERN.search(text.lower()) or _US_STATE.search(text))


def is_location_phrase(segment: str) -> bool:
    """True when a title suffix names a place ("remote", a country, region, or city)."""
    s = segment.strip()
    if not s:
        return False
    if _REMOTE_WORDS.search(s.lower()) or has_city(s):
        return True
    if find_regions(s)[0]:
        return True
    # Title segments are lower-cased by the caller, so match case-insensitively here.
    return bool(find_countries(s) or find_countries(s.upper()))
