"""Ícones locais de marcas e sugestões offline para o Cofre."""
import hashlib
import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont, ImageTk
import tkinter as tk


def normalizar(texto):
    """Converte texto em minúsculas ASCII e remove acentos, espaços e símbolos."""
    sem_acentos = unicodedata.normalize("NFKD", str(texto or ""))
    return re.sub(r"[^a-z0-9]+", "", sem_acentos.encode("ascii", "ignore").decode().casefold())

MARCAS = {
    "nubank": ("#820AD1", "Nu"), "itau": ("#EC7000", "Itaú"), "bradesco": ("#CC092F", "B"),
    "bancodobrasil": ("#F7D117", "BB"), "caixa": ("#005CA9", "CX"), "santander": ("#EC0000", "S"),
    "inter": ("#FF7A00", "I"), "c6bank": ("#242424", "C6"), "btgpactual": ("#001E62", "BTG"),
    "safra": ("#00205B", "S"), "sicredi": ("#3FA110", "Si"), "sicoob": ("#003641", "So"),
    "banrisul": ("#004B8D", "B"), "bancooriginal": ("#00A859", "O"), "neon": ("#00C8E6", "N"),
    "next": ("#00D95F", "N"), "willbank": ("#FFD400", "W"), "pagbank": ("#00A859", "PB"),
    "pagseguro": ("#00A859", "PS"), "picpay": ("#21C25E", "PP"), "mercadopago": ("#009EE3", "MP"),
    "paypal": ("#003087", "PP"), "pix": ("#32BCAD", "Pix"), "wise": ("#9FE870", "W"),
    "revolut": ("#0075EB", "R"), "bancopan": ("#0087CD", "P"), "banco24horas": ("#E30613", "24"),
    "ame": ("#E6007E", "A"), "recargapay": ("#00B1A9", "RP"), "99pay": ("#FFC20E", "99"),
    "stone": ("#00A868", "St"), "cielo": ("#00A3E0", "C"), "ton": ("#00D000", "T"),
    "sumup": ("#1D1F20", "SU"), "infinitepay": ("#00B140", "IP"),
    "xp": ("#111111", "XP"), "rico": ("#F26B21", "R"), "clear": ("#00A1E0", "C"),
    "nuinvest": ("#820AD1", "NI"), "genialinvestimentos": ("#00B2A9", "G"),
    "binance": ("#F0B90B", "B"), "mercadobitcoin": ("#F7931A", "MB"), "coinbase": ("#0052FF", "C"),
    "bitso": ("#2D9CDB", "B"), "metamask": ("#F6851B", "M"), "tradingview": ("#2962FF", "TV"),
    "instagram": ("#E4405F", "I"), "facebook": ("#1877F2", "f"), "whatsapp": ("#25D366", "W"),
    "telegram": ("#26A5E4", "T"), "x": ("#111111", "X"), "twitter": ("#1DA1F2", "T"),
    "tiktok": ("#111111", "TT"), "youtube": ("#FF0000", "YT"), "linkedin": ("#0A66C2", "in"),
    "pinterest": ("#E60023", "P"), "snapchat": ("#FFFC00", "S"), "reddit": ("#FF4500", "R"),
    "discord": ("#5865F2", "D"), "twitch": ("#9146FF", "T"), "threads": ("#111111", "@"),
    "kwai": ("#FF5000", "K"), "bluesky": ("#0085FF", "B"), "tumblr": ("#36465D", "t"),
    "signal": ("#3A76F0", "S"), "skype": ("#00AFF0", "S"), "messenger": ("#0084FF", "M"),
    "wechat": ("#07C160", "W"), "line": ("#06C755", "L"), "viber": ("#7360F2", "V"),
    "kick": ("#53FC18", "K"), "vk": ("#0077FF", "VK"), "quora": ("#B92B27", "Q"),
    "medium": ("#111111", "M"), "tinder": ("#FE3C72", "T"), "bumble": ("#FFC629", "B"),
    "badoo": ("#783BF9", "B"),
    "netflix": ("#E50914", "N"), "primevideo": ("#00A8E1", "PV"), "disneyplus": ("#113CCF", "D+"),
    "max": ("#002BE7", "max"), "hbomax": ("#5822B4", "HBO"), "globoplay": ("#F5253A", "G"),
    "paramountplus": ("#0064FF", "P+"), "appletv": ("#111111", "TV"), "crunchyroll": ("#F47521", "C"),
    "starplus": ("#0C1B3A", "S+"), "telecine": ("#E30613", "T"), "premiere": ("#00A859", "P"),
    "mubi": ("#111111", "M"), "plutotv": ("#FFD400", "P"), "tubi": ("#FA382F", "T"),
    "clarotv": ("#DA291C", "C"), "directv": ("#00A7E1", "D"), "skyplus": ("#E8003D", "S"),
    "vimeo": ("#1AB7EA", "V"), "dazn": ("#111111", "DZ"), "espn": ("#D00000", "E"),
    "looke": ("#E6007E", "L"), "univer": ("#00A3E0", "U"),
    "spotify": ("#1DB954", "S"), "deezer": ("#A238FF", "D"), "applemusic": ("#FA243C", "♪"),
    "youtubemusic": ("#FF0000", "YM"), "amazonmusic": ("#25D1DA", "AM"), "tidal": ("#111111", "T"),
    "soundcloud": ("#FF5500", "SC"), "audible": ("#F8991C", "A"), "napster": ("#111111", "N"),
    "google": ("#4285F4", "G"), "gmail": ("#EA4335", "M"), "googledrive": ("#1FA463", "D"),
    "googlecloud": ("#4285F4", "GC"), "outlook": ("#0078D4", "O"), "hotmail": ("#0078D4", "H"),
    "microsoft": ("#00A4EF", "MS"), "office365": ("#D83B01", "365"), "onedrive": ("#0078D4", "OD"),
    "teams": ("#6264A7", "T"), "azure": ("#0078D4", "Az"), "yahoo": ("#6001D2", "Y!"),
    "icloud": ("#3693F5", "iC"), "apple": ("#111111", "A"), "protonmail": ("#6D4AFF", "P"),
    "dropbox": ("#0061FF", "D"), "mega": ("#D9272E", "M"), "mediafire": ("#1299F3", "M"),
    "aws": ("#FF9900", "AWS"), "cloudflare": ("#F38020", "CF"), "digitalocean": ("#0080FF", "DO"),
    "github": ("#181717", "GH"), "gitlab": ("#FC6D26", "GL"), "bitbucket": ("#0052CC", "BB"),
    "stackoverflow": ("#F48024", "SO"), "npm": ("#CB3837", "npm"), "docker": ("#2496ED", "D"),
    "vercel": ("#111111", "▲"), "netlify": ("#00C7B7", "N"), "heroku": ("#430098", "H"),
    "chatgpt": ("#10A37F", "GPT"), "openai": ("#10A37F", "AI"), "claude": ("#D97757", "C"),
    "anthropic": ("#D97757", "A"), "gemini": ("#4285F4", "G"), "perplexity": ("#20808D", "P"),
    "midjourney": ("#111111", "MJ"), "huggingface": ("#FFD21E", "HF"),
    "notion": ("#111111", "N"), "slack": ("#4A154B", "S"), "zoom": ("#2D8CFF", "Z"),
    "canva": ("#00C4CC", "C"), "adobe": ("#FA0F00", "A"), "figma": ("#F24E1E", "F"),
    "trello": ("#0079BF", "T"), "asana": ("#F06A6A", "A"), "evernote": ("#00A82D", "E"),
    "googlemeet": ("#00897B", "M"), "calendly": ("#006BFF", "C"), "wordpress": ("#21759B", "W"),
    "wix": ("#0C6EFC", "W"), "shopify": ("#7AB55C", "S"), "godaddy": ("#1BDBDB", "G"),
    "hostinger": ("#673DE6", "H"), "registrobr": ("#00A859", "R"), "hostgator": ("#FFB300", "H"),
    "locaweb": ("#E30613", "L"), "umbler": ("#1E88E5", "U"), "kinghost": ("#F57C00", "K"),
    "amazon": ("#FF9900", "a"), "mercadolivre": ("#FFE600", "ML"), "shopee": ("#EE4D2D", "S"),
    "aliexpress": ("#E62E04", "Ali"), "magalu": ("#0086FF", "M"), "americanas": ("#E60014", "A"),
    "casasbahia": ("#0033A0", "CB"), "shein": ("#111111", "S"), "kabum": ("#FF6500", "K"),
    "olx": ("#6E0AD6", "OLX"), "temu": ("#FB7701", "T"), "amazonbr": ("#FF9900", "a"),
    "ifood": ("#EA1D2C", "iF"), "rappi": ("#FF441F", "R"), "ubereats": ("#06C167", "UE"),
    "ze": ("#FFC600", "Zé"), "americanasmarket": ("#E60014", "AM"), "carrefour": ("#004E9F", "C"),
    "pontofrio": ("#E30613", "PF"), "fastshop": ("#E30613", "FS"), "netshoes": ("#6A1B9A", "N"),
    "centauro": ("#E30613", "C"), "renner": ("#E30613", "R"), "zara": ("#111111", "Z"),
    "uber": ("#111111", "U"), "99": ("#FFC20E", "99"), "airbnb": ("#FF5A5F", "A"),
    "booking": ("#003B95", "B"), "decolar": ("#6A1B9A", "D"), "latam": ("#E30613", "L"),
    "gol": ("#FF7020", "G"), "azul": ("#0033A0", "Az"), "tripadvisor": ("#00AF87", "T"),
    "semparar": ("#00A859", "SP"), "conectcar": ("#E30613", "CC"), "waze": ("#33CCFF", "W"),
    "steam": ("#1B2838", "S"), "epicgames": ("#313131", "E"), "playstation": ("#003791", "PS"),
    "xbox": ("#107C10", "X"), "nintendo": ("#E60012", "N"), "riotgames": ("#D13639", "R"),
    "battlenet": ("#00AEFF", "B"), "ea": ("#FF4747", "EA"), "ubisoft": ("#0070FF", "U"),
    "roblox": ("#E2231A", "R"), "minecraft": ("#62B47A", "M"), "garena": ("#E31B23", "G"),
    "gog": ("#86328A", "G"), "origin": ("#F56C2D", "O"),
    "govbr": ("#1351B4", "gov"), "inss": ("#1351B4", "INSS"), "receitafederal": ("#1351B4", "RF"),
    "detran": ("#1351B4", "DT"), "sus": ("#1351B4", "SUS"), "cnh": ("#1351B4", "CNH"),
    "fgts": ("#005CA9", "FGTS"), "carteiradetrabalho": ("#1351B4", "CT"),
    "cartorio": ("#6B4F2A", "C"), "serasa": ("#C8102E", "S"), "spc": ("#0057A8", "SPC"),
    "sefaz": ("#1351B4", "SF"),
    "vivo": ("#660099", "V"), "claro": ("#DA291C", "C"), "tim": ("#004691", "TIM"),
    "oi": ("#FF6600", "oi"), "net": ("#F47920", "N"), "sabesp": ("#0072BC", "S"),
    "enel": ("#E30613", "E"), "cpfl": ("#00923F", "C"), "light": ("#F5A800", "L"),
    "equatorial": ("#00923F", "E"), "copel": ("#0072BC", "C"), "cemig": ("#00923F", "C"),
    "gympass": ("#FF5A00", "G"), "totalpass": ("#00A859", "TP"), "smartfit": ("#FFC400", "SF"),
    "unimed": ("#00995D", "U"), "amil": ("#00A3E0", "A"), "sulamerica": ("#FF6A00", "SA"),
    "hapvida": ("#00A859", "H"), "duolingo": ("#58CC02", "D"), "udemy": ("#A435F0", "U"),
    "coursera": ("#0056D2", "C"), "alura": ("#1C4DA1", "A"), "hotmart": ("#F04E23", "H"),
    "kiwify": ("#00A859", "K"), "eduzz": ("#FF6A00", "E"), "moodle": ("#F98012", "M"),
}

MARCAS_EXTRA = {
    "crefisa": ("#00A859", "Cr"), "bmg": ("#F26B21", "BMG"), "agibank": ("#00A3E0", "Agi"),
    "daycoval": ("#003B71", "Day"), "bancomercantil": ("#E30613", "Me"), "bancopine": ("#00A859", "Pi"),
    "bancobv": ("#0051A5", "BV"), "bancovotorantim": ("#0051A5", "BV"), "bancomaster": ("#1D1F20", "Ma"),
    "bancopaulista": ("#E30613", "BP"), "bancobradescard": ("#CC092F", "Bc"), "bancofibra": ("#00205B", "Fi"),
    "bancoabc": ("#00205B", "ABC"), "bancomodal": ("#1D1F20", "Mo"), "bancoc6": ("#242424", "C6"),
    "banese": ("#00A859", "Bn"), "banestes": ("#0051A5", "Bs"), "bancodonordeste": ("#E30613", "BNB"),
    "bancodaamazonia": ("#00A859", "BA"), "brb": ("#0051A5", "BRB"), "bancoarbi": ("#E30613", "Ar"),
    "facta": ("#00A859", "Fa"), "omni": ("#F26B21", "Om"), "solfacil": ("#00B140", "Sf"),
    "creditas": ("#00C896", "Cr"), "geru": ("#00A3E0", "Ge"), "simplic": ("#1D1F20", "Si"),
    "serasaemprestimos": ("#C8102E", "SE"), "consignado": ("#1351B4", "Con"),
    "visa": ("#1A1F71", "Vi"), "mastercard": ("#EB001B", "MC"), "elo": ("#00A4E0", "Elo"),
    "americanexpress": ("#006FCF", "Ax"), "hipercard": ("#B3131B", "Hi"), "alelo": ("#00A859", "Al"),
    "sodexo": ("#E30613", "So"), "ticket": ("#E30613", "Ti"), "vr": ("#00A859", "VR"),
    "ben": ("#6A1B9A", "Be"), "flash": ("#FF5A00", "Fl"), "pluxee": ("#E30613", "Pl"),
    "applepay": ("#111111", "Pay"), "googlepay": ("#4285F4", "GPay"), "samsungpay": ("#1428A0", "SP"),
    "mercadocredito": ("#009EE3", "MC"), "bancointer": ("#FF7A00", "I"), "nubankcartao": ("#820AD1", "Nu"),
    "portoseguro": ("#0051A5", "Po"), "azulseguros": ("#0033A0", "Az"), "tokiomarine": ("#E30613", "TM"),
    "allianz": ("#003781", "Al"), "liberty": ("#1D1F20", "Li"), "mapfre": ("#E30613", "Ma"),
    "bradescoseguros": ("#CC092F", "BS"), "itauseguros": ("#EC7000", "IS"), "youse": ("#00B2A9", "Yo"),
    "qualicorp": ("#E30613", "Qu"), "notredame": ("#00A3E0", "ND"), "prevent": ("#00A859", "PS"),
    "loterias": ("#005CA9", "LC"), "megasena": ("#209869", "MS"), "lotofacil": ("#930089", "LF"),
    "betano": ("#FF6A00", "Be"), "bet365": ("#027B5B", "365"), "betnacional": ("#00A859", "BN"),
    "blaze": ("#E30613", "Bl"), "pixbet": ("#00A859", "Px"), "sportingbet": ("#0051A5", "Sp"),
    "estrelabet": ("#FFC400", "Es"), "superbet": ("#E30613", "Su"), "novibet": ("#0051A5", "No"),
    "onlyfans": ("#00AFF0", "OF"), "patreon": ("#FF424D", "Pa"), "kofi": ("#FF5E5B", "Ko"),
    "tiktokshop": ("#111111", "TS"), "shopeeseller": ("#EE4D2D", "Sh"), "olxpay": ("#6E0AD6", "OP"),
    "imo": ("#0084FF", "imo"), "zalo": ("#0068FF", "Za"), "clubhouse": ("#F2E8D5", "Ch"),
    "linktree": ("#43E660", "Lt"), "behance": ("#1769FF", "Be"), "dribbble": ("#EA4C89", "Dr"),
    "deviantart": ("#05CC47", "DA"), "flickr": ("#0063DC", "Fl"), "goodreads": ("#553B08", "Gr"),
    "letterboxd": ("#00E054", "Lb"), "imdb": ("#F5C518", "IM"), "rottentomatoes": ("#FA320A", "RT"),
    "globoplayplus": ("#F5253A", "G+"), "sportv": ("#00A859", "Sp"), "combate": ("#E30613", "Co"),
    "bandplay": ("#0051A5", "Bp"), "recordplus": ("#E30613", "R+"), "sbtvideos": ("#FFC400", "SB"),
    "nowonline": ("#E30613", "Now"), "sky": ("#E8003D", "Sk"), "oitv": ("#FF6600", "Oi"),
    "vivotv": ("#660099", "VT"), "meliplus": ("#FFE600", "M+"), "nick": ("#FF6600", "Ni"),
    "discoveryplus": ("#2175D9", "D+"), "amcplus": ("#111111", "AMC"), "peacock": ("#111111", "Pe"),
    "hulu": ("#1CE783", "Hu"), "viki": ("#00A4E0", "Vi"), "kocowa": ("#E30613", "Ko"),
    "bandcamp": ("#629AA9", "Bc"), "twitchprime": ("#9146FF", "Tp"), "kindle": ("#F8991C", "Ki"),
    "kobo": ("#BF0000", "Ko"), "skeelo": ("#E30613", "Sk"), "scribd": ("#1E7B85", "Sc"),
    "epicgamesstore": ("#313131", "E"), "eaplay": ("#FF4747", "EA"), "xboxlive": ("#107C10", "X"),
    "psplus": ("#003791", "PS+"), "nintendoswitch": ("#E60012", "NS"), "rockstar": ("#FCAF17", "R*"),
    "bethesda": ("#111111", "Be"), "blizzard": ("#00AEFF", "Bz"), "valorant": ("#FD4556", "Va"),
    "freefire": ("#FFC400", "FF"), "pubg": ("#F2A900", "PU"), "fortnite": ("#3A1C71", "Fn"),
    "genshin": ("#5C8DFF", "Ge"), "mobilelegends": ("#E30613", "ML"), "clashroyale": ("#0F6FCF", "CR"),
    "clashofclans": ("#2E8B57", "CoC"), "supercell": ("#1D1F20", "Su"), "wargaming": ("#E30613", "Wg"),
    "gamersclub": ("#FF6A00", "GC"), "faceit": ("#FF5500", "Fa"), "hltv": ("#111111", "HL"),
    "cs2": ("#F2A900", "CS"), "dota2": ("#E30613", "D2"), "leagueoflegends": ("#C89B3C", "LoL"),
    "correios": ("#FFC400", "Co"), "totalexpress": ("#E30613", "TE"), "jadlog": ("#E30613", "Ja"),
    "loggi": ("#00A3E0", "Lo"), "melhorenvio": ("#0051A5", "ME"), "mercadoenvios": ("#FFE600", "ME"),
    "rastreamento": ("#FFC400", "Ra"), "azulcargo": ("#0033A0", "AC"), "gollog": ("#FF7020", "GL"),
    "tembici": ("#E30613", "Te"), "yellow": ("#FFE600", "Ye"), "bird": ("#111111", "Bi"),
    "maxima": ("#FFC400", "Mx"), "estapar": ("#E30613", "Es"), "zonaazul": ("#0051A5", "ZA"),
    "dpvat": ("#1351B4", "DP"), "cnhdigital": ("#1351B4", "CNHD"),
    "carteiradigitaldetransito": ("#1351B4", "CDT"), "detranmg": ("#1351B4", "DT"),
    "detransp": ("#1351B4", "DT"), "detranrj": ("#1351B4", "DT"), "ipva": ("#1351B4", "IPVA"),
    "iptu": ("#1351B4", "IPTU"), "prefeitura": ("#1351B4", "Pf"), "tribunal": ("#1351B4", "TJ"),
    "tjsp": ("#1351B4", "TJ"), "pje": ("#1351B4", "PJe"), "esaj": ("#1351B4", "eSAJ"),
    "certidao": ("#6B4F2A", "Cert"), "cartoriodigital": ("#6B4F2A", "CD"),
    "registrocivil": ("#6B4F2A", "RC"), "receitaws": ("#1351B4", "RW"), "cpf": ("#1351B4", "CPF"),
    "cnpj": ("#1351B4", "CNPJ"), "mei": ("#1351B4", "MEI"), "simplesnacional": ("#1351B4", "SN"),
    "nfe": ("#1351B4", "NFe"), "nfce": ("#1351B4", "NFCe"), "esocial": ("#1351B4", "eS"),
    "caixatem": ("#005CA9", "CT"), "bolsafamilia": ("#005CA9", "BF"), "cadunico": ("#1351B4", "CU"),
    "meuinss": ("#1351B4", "MI"), "valor": ("#1351B4", "Va"),
}
MARCAS = {**MARCAS_EXTRA, **MARCAS}

ALIASES = {
    "bb": "bancodobrasil", "bancodobrasil": "bancodobrasil", "itauunibanco": "itau",
    "caixaeconomica": "caixa", "caixaeconomicafederal": "caixa", "cef": "caixa", "c6": "c6bank",
    "btg": "btgpactual", "mp": "mercadopago", "mercadolivre": "mercadolivre", "meli": "mercadolivre",
    "ml": "mercadolivre", "hbo": "hbomax", "gov": "govbr", "governo": "govbr", "yt": "youtube",
    "fb": "facebook", "insta": "instagram", "zap": "whatsapp", "wpp": "whatsapp", "tt": "tiktok",
    "primevideo": "primevideo", "amazonprime": "primevideo", "prime": "primevideo", "disney": "disneyplus",
    "paramount": "paramountplus", "star": "starplus", "apple tv": "appletv", "gdrive": "googledrive",
    "drive": "googledrive", "gcloud": "googlecloud", "ms": "microsoft", "office": "office365",
    "m365": "office365", "gpt": "chatgpt", "epic": "epicgames", "psn": "playstation",
    "ps": "playstation", "riot": "riotgames", "lol": "riotgames", "receita": "receitafederal",
    "ir": "receitafederal", "carteira": "carteiradetrabalho", "ctps": "carteiradetrabalho",
    "ifoods": "ifood", "ubere": "ubereats", "noventaenove": "99", "banese": "banrisul",
}

ALIASES_EXTRA = {
    "bancobmg": "bmg", "bancocrefisa": "crefisa", "agi": "agibank", "bancoagibank": "agibank",
    "bancodaycoval": "daycoval", "pan": "bancopan", "bv": "bancobv", "mastercardbr": "mastercard",
    "amex": "americanexpress", "gpay": "googlepay", "porto": "portoseguro", "tokio": "tokiomarine",
    "notre": "notredame", "prevent": "prevent", "bet": "bet365", "betnac": "betnacional",
    "ml": "mercadolivre", "ps5": "playstation", "ps4": "playstation", "ff": "freefire",
    "lol": "leagueoflegends", "valo": "valorant", "cs": "cs2", "csgo": "cs2", "dota": "dota2",
    "coc": "clashofclans", "cr": "clashroyale", "gc": "gamersclub", "eaf": "ea",
    "correio": "correios", "ect": "correios", "mercadoenvio": "mercadoenvios",
    "e-social": "esocial", "pjeweb": "pje", "tjrj": "tribunal", "tjmg": "tribunal", "trf": "tribunal",
}
ALIASES = {**ALIASES_EXTRA, **ALIASES}

NOMES = {
    "bancodobrasil": "Banco do Brasil", "mercadopago": "Mercado Pago", "primevideo": "Prime Video",
    "disneyplus": "Disney+", "hbomax": "HBO Max", "googledrive": "Google Drive",
    "receitafederal": "Receita Federal", "govbr": "Gov.br", "ifood": "iFood",
    "youtubemusic": "YouTube Music", "c6bank": "C6 Bank", "btgpactual": "BTG Pactual",
    "bancooriginal": "Banco Original", "bancopan": "Banco Pan", "banco24horas": "Banco24Horas",
    "genialinvestimentos": "Genial Investimentos", "mercadobitcoin": "Mercado Bitcoin",
    "paramountplus": "Paramount+", "appletv": "Apple TV", "crunchyroll": "Crunchyroll",
    "starplus": "Star+", "googlecloud": "Google Cloud", "office365": "Office 365",
    "protonmail": "Proton Mail", "digitalocean": "DigitalOcean", "stackoverflow": "Stack Overflow",
    "epicgames": "Epic Games", "riotgames": "Riot Games", "ubereats": "Uber Eats",
    "americanasmarket": "Americanas Market", "tripadvisor": "Tripadvisor",
    "semparar": "Sem Parar", "conectcar": "ConectCar", "govbr": "Gov.br",
    "receitafederal": "Receita Federal", "carteiradetrabalho": "Carteira de Trabalho",
    "totalpass": "TotalPass", "smartfit": "Smart Fit",
}

_ALIAS_NORMALIZADOS = {normalizar(alias): chave for alias, chave in ALIASES.items()
                       if normalizar(alias) and chave in MARCAS}


def _nome_exibicao(chave):
    if chave in NOMES:
        return NOMES[chave]
    return chave[:1].upper() + chave[1:]


def achar_marca(texto):
    """Resolve uma marca por alias/nome exato e, para nomes longos, por inclusão."""
    nome = normalizar(texto)
    if not nome:
        return None
    chave = _ALIAS_NORMALIZADOS.get(nome)
    if chave:
        return chave
    if nome in MARCAS:
        return nome
    if len(nome) < 3:
        return None
    for marca in MARCAS:
        if marca in nome or nome in marca:
            return marca
    return None


def sugerir(texto, limite=6):
    """Retorna marcas iniciadas pelo termo, depois marcas que o contêm e aliases iniciados."""
    busca = normalizar(texto)
    if not busca or limite <= 0:
        return []
    encontradas = []
    vistas = set()

    def incluir(chave):
        if chave in MARCAS and chave not in vistas and len(encontradas) < limite:
            vistas.add(chave)
            encontradas.append((chave, _nome_exibicao(chave)))

    for chave in MARCAS:
        if chave.startswith(busca):
            incluir(chave)
    if len(busca) > 1:
        for chave in MARCAS:
            if busca in chave:
                incluir(chave)
    for alias in _ALIAS_NORMALIZADOS:
        if alias.startswith(busca):
            incluir(_ALIAS_NORMALIZADOS[alias])
    return encontradas


_CACHE_ICONES = {}


def _cor_da_marca(nome, chave):
    if chave:
        return MARCAS[chave][0], MARCAS[chave][1]
    chave_hash = normalizar(nome)
    digest = hashlib.md5(chave_hash.encode("utf-8")).digest()
    return "#{:02X}{:02X}{:02X}".format(*digest[:3]), (str(nome or "").strip()[:1].upper() or "?")


def icone(nome, tam=24, master=None):
    """Cria um ícone de marca desenhado localmente e mantém PhotoImage vivo no cache."""
    tamanho = max(1, int(tam))
    chave = achar_marca(nome)
    normalizado = chave or normalizar(nome)
    cor, sigla = _cor_da_marca(nome, chave)
    if master is None:
        try:
            import tkinter as tk
            master = tk._default_root
        except ImportError:
            master = None
    interprete = id(master.tk) if master is not None else None
    identificador = normalizado or (str(nome or "").strip()[:1] or "?")
    cache_key = (identificador, tamanho, interprete)
    if cache_key in _CACHE_ICONES:
        return _CACHE_ICONES[cache_key]

    escala = 4
    lado = tamanho * escala
    fundo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    draw = ImageDraw.Draw(fundo)
    rgb = tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))
    draw.rounded_rectangle((0, 0, lado - 1, lado - 1), radius=max(1, lado // 5), fill=rgb + (255,))
    luminancia = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])
    tinta = (0, 0, 0, 255) if luminancia > 170 else (255, 255, 255, 255)
    caminho_fonte = r"C:\Windows\Fonts\arialbd.ttf"
    try:
        fonte = ImageFont.truetype(caminho_fonte, max(8, int(lado * 0.42)))
    except OSError:
        caminho_fonte = None
        fonte = ImageFont.load_default()
    texto = sigla or "?"
    margem = lado * 0.12
    try:
        if caminho_fonte:
            for tamanho_fonte in range(max(8, int(lado * 0.42)), 7, -2):
                fonte = ImageFont.truetype(caminho_fonte, tamanho_fonte)
                caixa = draw.textbbox((0, 0), texto, font=fonte)
                largura = caixa[2] - caixa[0]
                altura = caixa[3] - caixa[1]
                if largura <= lado - 2 * margem and altura <= lado - 2 * margem:
                    break
        caixa = draw.textbbox((0, 0), texto, font=fonte)
        largura = caixa[2] - caixa[0]
        altura = caixa[3] - caixa[1]
        draw.text(((lado - largura) / 2 - caixa[0], (lado - altura) / 2 - caixa[1]),
                  texto, font=fonte, fill=tinta)
    except (OSError, UnicodeEncodeError):
        draw.text((lado * 0.3, lado * 0.25), "?", font=ImageFont.load_default(), fill=tinta)
    resampling = getattr(Image, "Resampling", Image)
    imagem = fundo.resize((tamanho, tamanho), resampling.LANCZOS)
    kwargs = {"master": master} if master is not None else {}
    foto = ImageTk.PhotoImage(imagem, **kwargs)
    _CACHE_ICONES[cache_key] = foto
    return foto


class AutocompletarMarcas:
    """Sugestões acessíveis por teclado e mouse, sem janelas ou conexões extras."""

    def __init__(self, campo, previsualizacao, lista, limite=6):
        self.campo = campo
        self.previsualizacao = previsualizacao
        self._previsualizacao_em_grade = previsualizacao.winfo_manager() == "grid"
        self.lista = lista
        self.limite = max(1, int(limite))
        self.resultados = []
        self.indice = -1
        self._fechar_pendente = None
        self.botoes = []
        self.lista.columnconfigure(0, weight=1)
        for indice in range(self.limite):
            botao = tk.Button(
                self.lista, text="", compound="left", anchor="w", takefocus=0,
                font=("Segoe UI", 10), relief="flat", bd=0, highlightthickness=0,
                padx=8, pady=4, bg="#202430", fg="#f0f2f8",
                activebackground="#30374a", activeforeground="#ffffff",
                command=lambda i=indice: self.escolher(i))
            botao.grid(row=indice, column=0, sticky="ew")
            botao.grid_remove()
            self.botoes.append(botao)
        self.lista.grid_remove()
        self.campo.bind("<KeyRelease>", self._ao_digitar, add="+")
        self.campo.bind("<Down>", lambda evento: self._navegar(evento, 1), add="+")
        self.campo.bind("<Up>", lambda evento: self._navegar(evento, -1), add="+")
        self.campo.bind("<Return>", self._ao_enter, add="+")
        self.campo.bind("<Escape>", self._ao_escape, add="+")
        self.campo.bind("<FocusOut>", self._ao_perder_foco, add="+")
        self.atualizar_previsualizacao()

    def atualizar_previsualizacao(self):
        texto = self.campo.get().strip()
        if not texto:
            self.previsualizacao.configure(image="")
            self.previsualizacao.image = None
            if self._previsualizacao_em_grade:
                self.previsualizacao.grid_remove()
            return
        foto = icone(texto, 24, master=self.previsualizacao)
        self.previsualizacao.configure(image=foto)
        self.previsualizacao.image = foto
        if self._previsualizacao_em_grade:
            self.previsualizacao.grid()

    def atualizar(self):
        self.atualizar_previsualizacao()
        self.resultados = sugerir(self.campo.get(), self.limite)
        self.indice = -1
        if not self.resultados:
            self.fechar()
            return
        for indice, botao in enumerate(self.botoes):
            if indice >= len(self.resultados):
                botao.grid_remove()
                continue
            chave, nome = self.resultados[indice]
            foto = icone(chave, 24, master=botao)
            botao.configure(text=" " + nome, image=foto, bg="#202430")
            botao.image = foto
            botao.grid()
        self.lista.grid()

    def fechar(self):
        self.lista.grid_remove()
        for botao in self.botoes:
            botao.grid_remove()
        self.indice = -1
        self.resultados = []

    def escolher(self, indice):
        if not 0 <= indice < len(self.resultados):
            return
        _, nome = self.resultados[indice]
        self.campo.delete(0, "end")
        self.campo.insert(0, nome)
        self.atualizar_previsualizacao()
        self.fechar()
        self.campo.focus_set()

    def _ao_digitar(self, evento=None):
        if evento is None or evento.keysym not in ("Up", "Down", "Return", "Escape"):
            self.atualizar()

    def _navegar(self, evento, passo):
        if not self.resultados:
            self.resultados = sugerir(self.campo.get(), self.limite)
            if not self.resultados:
                return None
            for indice, (chave, nome) in enumerate(self.resultados):
                botao = self.botoes[indice]
                foto = icone(chave, 24, master=botao)
                botao.configure(text=" " + nome, image=foto)
                botao.image = foto
                botao.grid()
            self.lista.grid()
        self.indice = min(len(self.resultados) - 1, max(0, self.indice + passo))
        for indice, botao in enumerate(self.botoes):
            if indice < len(self.resultados):
                botao.configure(bg="#343d54" if indice == self.indice else "#202430")
        return "break"

    def _ao_enter(self, evento=None):
        if not self.resultados:
            return None
        self.escolher(self.indice if self.indice >= 0 else 0)
        return "break"

    def _ao_escape(self, evento=None):
        if self.resultados:
            self.fechar()
            return "break"
        return None

    def _ao_perder_foco(self, evento=None):
        if self._fechar_pendente is not None:
            try:
                self.campo.after_cancel(self._fechar_pendente)
            except tk.TclError:
                pass
        try:
            self._fechar_pendente = self.campo.after(150, self._fechar_se_foco_fora)
        except tk.TclError:
            self._fechar_pendente = None

    def _fechar_se_foco_fora(self):
        self._fechar_pendente = None
        try:
            foco = self.campo.winfo_toplevel().focus_get()
        except tk.TclError:
            foco = None
        if foco is not self.campo and foco not in self.botoes:
            self.fechar()

