import telebot
from telebot import types
import sqlite3
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
from datetime import datetime, timedelta
import re
import logging
import os
import requests
import json
import hashlib
import qrcode
import io
import base64
from PIL import Image
import random
import time
import string
import uuid

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8428612777:AAFkQx5-_AuuR2qW2p1vV4Bz0csZVJJa7D8')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '8560355079').split(',')]
MAX_FREE_REQUESTS = 3
CHANNEL_USERNAME = "@LifeStanOsint"
CHANNEL_LINK = "https://t.me/LifeStanOsint"
CURRENCY_NAME = "💸"
SUBSCRIPTION_REQUIRED = True
REFERRAL_BONUS = 5
PROMO_CODE_LENGTH = 8

bot = telebot.TeleBot(TOKEN)

# --- БАЗА ДАННЫХ ---
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('osint.db', check_same_thread=False)
    c = conn.cursor()
    
    # Пользователи
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  last_name TEXT,
                  is_premium INTEGER DEFAULT 0,
                  premium_expiry TEXT,
                  request_count INTEGER DEFAULT 0,
                  last_request_date TEXT,
                  join_date TEXT DEFAULT CURRENT_TIMESTAMP,
                  is_banned INTEGER DEFAULT 0,
                  balance INTEGER DEFAULT 100,
                  total_requests INTEGER DEFAULT 0,
                  subscribed INTEGER DEFAULT 0,
                  referral_code TEXT UNIQUE,
                  referred_by TEXT,
                  vip_level INTEGER DEFAULT 0,
                  daily_bonus_claimed TEXT DEFAULT '')''')
    
    # Транзакции
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount INTEGER,
                  type TEXT,
                  description TEXT,
                  date TEXT DEFAULT CURRENT_TIMESTAMP)''')
    
    # Запросы
    c.execute('''CREATE TABLE IF NOT EXISTS requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  query_type TEXT,
                  query_data TEXT,
                  result TEXT,
                  cost INTEGER DEFAULT 1,
                  timestamp TEXT DEFAULT CURRENT_TIMESTAMP)''')
    
    # Промокоды
    c.execute('''CREATE TABLE IF NOT EXISTS promocodes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  code TEXT UNIQUE,
                  amount INTEGER,
                  uses_total INTEGER DEFAULT 1,
                  uses_left INTEGER DEFAULT 1,
                  created_by INTEGER,
                  created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                  expiry_date TEXT,
                  is_active INTEGER DEFAULT 1,
                  description TEXT)''')
    
    # Использованные промокоды
    c.execute('''CREATE TABLE IF NOT EXISTS promocode_usage
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  promocode_id INTEGER,
                  used_date TEXT DEFAULT CURRENT_TIMESTAMP)''')
    
    # Рефералы
    c.execute('''CREATE TABLE IF NOT EXISTS referrals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  referrer_id INTEGER,
                  referred_id INTEGER,
                  bonus_paid INTEGER DEFAULT 0,
                  date TEXT DEFAULT CURRENT_TIMESTAMP)''')
    
    # Настройки
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

# --- МИРОВЫЕ ОПЕРАТОРЫ СВЯЗИ (ПОЛНАЯ БАЗА) ---
WORLD_OPERATORS = {
    # Россия
    'RU': {
        'МегаФон': ['920', '921', '922', '923', '924', '925', '926', '927', '928', '929', 
                   '930', '931', '932', '933', '934', '935', '936', '937', '938', '939'],
        'МТС': ['910', '911', '912', '913', '914', '915', '916', '917', '918', '919',
               '980', '981', '982', '983', '984', '985', '986', '987', '988', '989'],
        'Билайн': ['900', '902', '903', '904', '905', '906', '909', '950', '951', '952',
                  '953', '960', '961', '962', '963', '964', '965', '966', '967', '968', '969'],
        'Tele2': ['900', '901', '902', '904', '908', '950', '951', '952', '953', '958'],
        'Yota': ['995', '996'],
        'Ростелеком': ['900', '901', '902', '904', '908', '950', '951', '952', '953', '958'],
    },
    
    # Украина
    'UA': {
        'Kyivstar': ['67', '68', '96', '97', '98'],
        'Vodafone': ['50', '66', '95', '99'],
        'lifecell': ['63', '73', '93'],
        '3mob': ['91'],
        'People.net': ['92'],
    },
    
    # Казахстан
    'KZ': {
        'Beeline': ['705', '777', '701', '702', '708'],
        'Tele2': ['747', '700'],
        'Kcell': ['700', '701', '702', '705', '707', '708'],
        'Altel': ['700', '708'],
    },
    
    # Беларусь
    'BY': {
        'МТС': ['29', '33'],
        'A1': ['29', '44'],
        'life:)': ['25'],
    },
    
    # США
    'US': {
        'Verizon': ['201', '202', '203', '205', '206', '207', '208', '209', '210'],
        'AT&T': ['205', '206', '207', '208', '209', '210', '212', '213', '214'],
        'T-Mobile': ['209', '210', '211', '212', '213', '214', '215', '216', '217'],
        'Sprint': ['308', '309', '310', '311', '312', '313', '314', '315', '316'],
    },
    
    # Китай
    'CN': {
        'China Mobile': ['134', '135', '136', '137', '138', '139', '150', '151', '152', 
                        '157', '158', '159', '182', '183', '184', '187', '188'],
        'China Unicom': ['130', '131', '132', '155', '156', '185', '186'],
        'China Telecom': ['133', '153', '180', '189'],
    },
    
    # Германия
    'DE': {
        'Telekom': ['151', '152', '157', '159', '160', '162', '163', '170', '171', '172', '173', '174', '175', '176', '177', '178', '179'],
        'Vodafone': ['151', '152', '157', '159', '160', '162', '163', '170', '171', '172', '173', '174', '175', '176', '177', '178', '179'],
        'O2': ['151', '152', '157', '159', '160', '162', '163', '170', '171', '172', '173', '174', '175', '176', '177', '178', '179'],
    },
    
    # Великобритания
    'GB': {
        'EE': ['744', '745', '746', '747', '748', '749', '750', '751', '752', '753', '754', '755', '756', '757', '758', '759'],
        'O2': ['770', '771', '772', '773', '774', '775', '776', '777', '778', '779'],
        'Vodafone': ['744', '745', '746', '747', '748', '749', '750', '751', '752', '753', '754', '755', '756', '757', '758', '759'],
        'Three': ['743', '744', '745', '746', '747', '748', '749'],
    },
    
    # Турция
    'TR': {
        'Turkcell': ['530', '531', '532', '533', '534', '535', '536', '537', '538', '539'],
        'Vodafone': ['540', '541', '542', '543', '544', '545', '546', '547', '548', '549'],
        'Türk Telekom': ['501', '502', '503', '504', '505', '506', '507', '508', '509'],
    },
    
    # Индия
    'IN': {
        'Airtel': ['740', '741', '742', '743', '744', '745', '746', '747', '748', '749'],
        'Vodafone Idea': ['700', '701', '702', '703', '704', '705', '706', '707', '708', '709'],
        'Jio': ['600', '601', '602', '603', '604', '605', '606', '607', '608', '609'],
    },
    
    # Бразилия
    'BR': {
        'Vivo': ['15', '16', '17', '18', '19'],
        'Claro': ['21', '22', '24'],
        'TIM': ['31', '32', '33'],
        'Oi': ['14', '31', '41'],
    },
    
    # Мексика
    'MX': {
        'Telcel': ['044', '045'],
        'Movistar': ['044', '045'],
        'AT&T Mexico': ['044', '045'],
    },
    
    # Италия
    'IT': {
        'TIM': ['320', '321', '322', '323', '324', '325', '326', '327', '328', '329'],
        'Vodafone': ['340', '341', '342', '343', '344', '345', '346', '347', '348', '349'],
        'Wind Tre': ['330', '331', '332', '333', '334', '335', '336', '337', '338', '339'],
    },
    
    # Франция
    'FR': {
        'Orange': ['06', '07'],
        'SFR': ['06', '07'],
        'Bouygues Telecom': ['06', '07'],
        'Free Mobile': ['06', '07'],
    },
    
    # Испания
    'ES': {
        'Movistar': ['6'],
        'Vodafone': ['6'],
        'Orange': ['6'],
        'Yoigo': ['6'],
    },
    
    # Польша
    'PL': {
        'Orange': ['50', '51', '53', '54', '55', '57', '58', '59'],
        'T-Mobile': ['50', '51', '53', '54', '55', '57', '58', '59'],
        'Play': ['50', '51', '53', '54', '55', '57', '58', '59'],
    },
    
    # Япония
    'JP': {
        'NTT Docomo': ['090', '080', '070'],
        'au': ['090', '080', '070'],
        'SoftBank': ['090', '080', '070'],
        'Rakuten Mobile': ['090', '080', '070'],
    },
    
    # Южная Корея
    'KR': {
        'SK Telecom': ['010'],
        'KT': ['010'],
        'LG U+': ['010'],
    },
    
    # Индонезия
    'ID': {
        'Telkomsel': ['0811', '0812', '0813', '0821', '0822', '0823', '0852', '0853', '0851'],
        'Indosat': ['0814', '0815', '0816', '0855', '0856', '0857', '0858'],
        'XL Axiata': ['0817', '0818', '0819', '0859', '0877', '0878'],
    },
    
    # Египет
    'EG': {
        'Vodafone Egypt': ['010'],
        'Orange Egypt': ['012'],
        'Etisalat Egypt': ['011'],
        'WE': ['015'],
    },
    
    # Саудовская Аравия
    'SA': {
        'STC': ['050', '051', '052', '053', '054', '055', '056', '057', '058', '059'],
        'Mobily': ['050', '051', '052', '053', '054', '055', '056', '057', '058', '059'],
        'Zain': ['050', '051', '052', '053', '054', '055', '056', '057', '058', '059'],
    },
    
    # ОАЭ
    'AE': {
        'Etisalat': ['050', '055', '056', '058'],
        'du': ['050', '055', '056', '058'],
    },
    
    # Израиль
    'IL': {
        'Cellcom': ['052', '053', '054', '055', '056', '057', '058', '059'],
        'Partner': ['050', '051', '052', '053', '054', '055', '056', '057', '058', '059'],
        'Pelephone': ['050', '051', '052', '053', '054', '055', '056', '057', '058', '059'],
    },
    
    # ЮАР
    'ZA': {
        'Vodacom': ['082'],
        'MTN': ['083'],
        'Cell C': ['084'],
        'Telkom': ['081'],
    },
    
    # Австралия
    'AU': {
        'Telstra': ['04'],
        'Optus': ['04'],
        'Vodafone': ['04'],
    },
    
    # Канада
    'CA': {
        'Rogers': ['416', '647', '437'],
        'Bell': ['416', '647', '437'],
        'Telus': ['416', '647', '437'],
    },
    
    # Нидерланды
    'NL': {
        'KPN': ['06'],
        'Vodafone': ['06'],
        'T-Mobile': ['06'],
    },
    
    # Швеция
    'SE': {
        'Telia': ['070', '072', '076'],
        'Tele2': ['072', '073', '076'],
        'Telenor': ['070', '072', '076'],
    },
    
    # Норвегия
    'NO': {
        'Telenor': ['90', '91', '92', '93', '94', '95', '96', '97', '98', '99'],
        'Telia': ['90', '91', '92', '93', '94', '95', '96', '97', '98', '99'],
        'Ice': ['90', '91', '92', '93', '94', '95', '96', '97', '98', '99'],
    },
    
    # Дания
    'DK': {
        'TDC': ['20', '21', '22', '23', '24', '25', '26', '27', '28', '29'],
        'Telenor': ['20', '21', '22', '23', '24', '25', '26', '27', '28', '29'],
        '3': ['30', '31', '32', '33', '34', '35', '36', '37', '38', '39'],
    },
    
    # Финляндия
    'FI': {
        'Elisa': ['040', '041', '042', '043', '044', '045', '046', '047', '048', '049'],
        'DNA': ['040', '041', '042', '043', '044', '045', '046', '047', '048', '049'],
        'Telia': ['040', '041', '042', '043', '044', '045', '046', '047', '048', '049'],
    },
    
    # Швейцария
    'CH': {
        'Swisscom': ['076', '077', '078', '079'],
        'Sunrise': ['076', '077', '078', '079'],
        'Salt': ['076', '077', '078', '079'],
    },
    
    # Австрия
    'AT': {
        'A1': ['0660', '0661', '0662', '0663', '0664'],
        'T-Mobile': ['0660', '0661', '0662', '0663', '0664'],
        'Drei': ['0660', '0661', '0662', '0663', '0664'],
    },
    
    # Бельгия
    'BE': {
        'Proximus': ['0470', '0471', '0472', '0473', '0474', '0475', '0476', '0477', '0478', '0479'],
        'Orange': ['0460', '0461', '0462', '0463', '0464', '0465', '0466', '0467', '0468', '0469'],
        'Base': ['0480', '0481', '0482', '0483', '0484', '0485', '0486', '0487', '0488', '0489'],
    },
    
    # Португалия
    'PT': {
        'Vodafone': ['91', '92', '93', '96'],
        'MEO': ['91', '92', '93', '96'],
        'NOS': ['91', '92', '93', '96'],
    },
    
    # Греция
    'GR': {
        'Cosmote': ['690', '691', '692', '693', '694', '695', '696', '697', '698', '699'],
        'Vodafone': ['690', '691', '692', '693', '694', '695', '696', '697', '698', '699'],
        'Wind': ['690', '691', '692', '693', '694', '695', '696', '697', '698', '699'],
    },
    
    # Чехия
    'CZ': {
        'O2': ['72', '73', '74', '75', '76', '77', '78', '79'],
        'T-Mobile': ['72', '73', '74', '75', '76', '77', '78', '79'],
        'Vodafone': ['72', '73', '74', '75', '76', '77', '78', '79'],
    },
    
    # Венгрия
    'HU': {
        'Telekom': ['20', '30', '70'],
        'Telenor': ['20', '30', '70'],
        'Vodafone': ['20', '30', '70'],
    },
    
    # Румыния
    'RO': {
        'Vodafone': ['72', '73', '74', '75', '76', '77', '78', '79'],
        'Orange': ['72', '73', '74', '75', '76', '77', '78', '79'],
        'Telekom': ['72', '73', '74', '75', '76', '77', '78', '79'],
    },
    
    # Болгария
    'BG': {
        'Vivacom': ['87', '88', '89'],
        'A1': ['87', '88', '89'],
        'Telenor': ['87', '88', '89'],
    },
    
    # Сербия
    'RS': {
        'Telekom Srbija': ['60', '61', '62', '63', '64', '65', '66', '67', '68', '69'],
        'Telenor': ['60', '61', '62', '63', '64', '65', '66', '67', '68', '69'],
        'Vip': ['60', '61', '62', '63', '64', '65', '66', '67', '68', '69'],
    },
    
    # Хорватия
    'HR': {
        'T-Mobile': ['91', '92', '95', '97', '98'],
        'Vip': ['91', '92', '95', '97', '98'],
        'Tele2': ['91', '92', '95', '97', '98'],
    },
    
    # Словакия
    'SK': {
        'Orange': ['90', '91', '92', '93', '94', '95', '96', '97', '98', '99'],
        'Telekom': ['90', '91', '92', '93', '94', '95', '96', '97', '98', '99'],
        'O2': ['90', '91', '92', '93', '94', '95', '96', '97', '98', '99'],
    },
    
    # Словения
    'SI': {
        'Telekom': ['040', '041', '042', '043', '044', '045', '046', '047', '048', '049'],
        'A1': ['040', '041', '042', '043', '044', '045', '046', '047', '048', '049'],
        'Telemach': ['040', '041', '042', '043', '044', '045', '046', '047', '048', '049'],
    },
    
    # Литва
    'LT': {
        'Telia': ['60', '61', '62', '63', '64', '65', '66', '67', '68', '69'],
        'Bitė': ['60', '61', '62', '63', '64', '65', '66', '67', '68', '69'],
        'Tele2': ['60', '61', '62', '63', '64', '65', '66', '67', '68', '69'],
    },
    
    # Латвия
    'LV': {
        'LMT': ['20', '21', '22', '23', '24', '25', '26', '27', '28', '29'],
        'Tele2': ['20', '21', '22', '23', '24', '25', '26', '27', '28', '29'],
        'Bite': ['20', '21', '22', '23', '24', '25', '26', '27', '28', '29'],
    },
    
    # Эстония
    'EE': {
        'Telia': ['50', '51', '52', '53', '54', '55', '56', '57', '58', '59'],
        'Elisa': ['50', '51', '52', '53', '54', '55', '56', '57', '58', '59'],
        'Tele2': ['50', '51', '52', '53', '54', '55', '56', '57', '58', '59'],
    },
}

# Названия стран
COUNTRY_NAMES = {
    'RU': 'Россия', 'US': 'США', 'GB': 'Великобритания', 'DE': 'Германия',
    'FR': 'Франция', 'IT': 'Италия', 'ES': 'Испания', 'UA': 'Украина',
    'BY': 'Беларусь', 'KZ': 'Казахстан', 'CN': 'Китай', 'JP': 'Япония',
    'KR': 'Южная Корея', 'IN': 'Индия', 'BR': 'Бразилия', 'MX': 'Мексика',
    'TR': 'Турция', 'PL': 'Польша', 'ID': 'Индонезия', 'EG': 'Египет',
    'SA': 'Саудовская Аравия', 'AE': 'ОАЭ', 'IL': 'Израиль', 'ZA': 'ЮАР',
    'AU': 'Австралия', 'CA': 'Канада', 'NL': 'Нидерланды', 'SE': 'Швеция',
    'NO': 'Норвегия', 'FI': 'Финляндия', 'DK': 'Дания', 'CH': 'Швейцария',
    'AT': 'Австрия', 'BE': 'Бельгия', 'PT': 'Португалия', 'GR': 'Греция',
    'CZ': 'Чехия', 'HU': 'Венгрия', 'RO': 'Румыния', 'BG': 'Болгария',
    'RS': 'Сербия', 'HR': 'Хорватия', 'SK': 'Словакия', 'SI': 'Словения',
    'LT': 'Литва', 'LV': 'Латвия', 'EE': 'Эстония',
}

# Регионы России
RUSSIAN_REGIONS = {
    '77': 'Москва', '78': 'Санкт-Петербург',
    '01': 'Адыгея', '02': 'Башкортостан', '03': 'Бурятия', '04': 'Алтай',
    '05': 'Дагестан', '06': 'Ингушетия', '07': 'Кабардино-Балкария', '08': 'Калмыкия',
    '09': 'Карачаево-Черкесия', '10': 'Карелия', '11': 'Коми', '12': 'Марий Эл',
    '13': 'Мордовия', '14': 'Якутия', '15': 'Северная Осетия', '16': 'Татарстан',
    '17': 'Тыва', '18': 'Удмуртия', '19': 'Хакасия', '21': 'Чувашия',
    '22': 'Алтайский край', '23': 'Краснодарский край', '24': 'Красноярский край',
    '25': 'Приморский край', '26': 'Ставропольский край', '27': 'Хабаровский край',
    '28': 'Амурская область', '29': 'Архангельская область', '30': 'Астраханская область',
    '31': 'Белгородская область', '32': 'Брянская область', '33': 'Владимирская область',
    '34': 'Волгоградская область', '35': 'Вологодская область', '36': 'Воронежская область',
    '37': 'Ивановская область', '38': 'Иркутская область', '39': 'Калининградская область',
    '40': 'Калужская область', '41': 'Камчатский край', '42': 'Кемеровская область',
    '43': 'Кировская область', '44': 'Костромская область', '45': 'Курганская область',
    '46': 'Курская область', '47': 'Ленинградская область', '48': 'Липецкая область',
    '49': 'Магаданская область', '50': 'Московская область', '51': 'Мурманская область',
    '52': 'Нижегородская область', '53': 'Новгородская область', '54': 'Новосибирская область',
    '55': 'Омская область', '56': 'Оренбургская область', '57': 'Орловская область',
    '58': 'Пензенская область', '59': 'Пермский край', '60': 'Псковская область',
    '61': 'Ростовская область', '62': 'Рязанская область', '63': 'Самарская область',
    '64': 'Саратовская область', '65': 'Сахалинская область', '66': 'Свердловская область',
    '67': 'Смоленская область', '68': 'Тамбовская область', '69': 'Тверская область',
    '70': 'Томская область', '71': 'Тульская область', '72': 'Тюменская область',
    '73': 'Ульяновская область', '74': 'Челябинская область', '75': 'Забайкальский край',
    '76': 'Ярославская область', '79': 'Еврейская автономная область', '83': 'Ненецкий АО',
    '86': 'Ханты-Мансийский АО', '87': 'Чукотский АО', '89': 'Ямало-Ненецкий АО',
    '91': 'Крым', '92': 'Севастополь'
}

# --- УТИЛИТЫ ---
def is_admin(user_id):
    """Проверка прав администратора"""
    return user_id in ADMIN_IDS

def get_user_balance(user_id):
    """Получить баланс пользователя"""
    conn = sqlite3.connect('osint.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def update_balance(user_id, amount, transaction_type="system", description=""):
    """Обновить баланс пользователя"""
    conn = sqlite3.connect('osint.db')
    c = conn.cursor()
    
    try:
        # Обновляем баланс
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        
        # Записываем транзакцию
        c.execute("""INSERT INTO transactions (user_id, amount, type, description) 
                     VALUES (?, ?, ?, ?)""", 
                  (user_id, amount, transaction_type, description))
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления баланса: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def generate_promo_code():
    """Генерация промокода"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=PROMO_CODE_LENGTH))

def create_promo_code(amount, uses_total=1, expiry_days=30, description="", created_by=0):
    """Создать промокод"""
    conn = sqlite3.connect('osint.db')
    c = conn.cursor()
    
    code = generate_promo_code()
    expiry_date = (datetime.now() + timedelta(days=expiry_days)).strftime("%Y-%m-%d") if expiry_days > 0 else None
    
    try:
        c.execute("""INSERT INTO promocodes 
                     (code, amount, uses_total, uses_left, created_by, expiry_date, description) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (code, amount, uses_total, uses_total, created_by, expiry_date, description))
        conn.commit()
        return code
    except sqlite3.IntegrityError:
        # Если промокод уже существует, генерируем новый
        return create_promo_code(amount, uses_total, expiry_days, description, created_by)
    except Exception as e:
        logger.error(f"Ошибка создания промокода: {e}")
        return None
    finally:
        conn.close()

def use_promo_code(user_id, code):
    """Активировать промокод"""
    conn = sqlite3.connect('osint.db')
    c = conn.cursor()
    
    try:
        # Проверяем промокод
        c.execute("""SELECT id, amount, uses_left, expiry_date, is_active 
                     FROM promocodes WHERE code = ?""", (code,))
        promo = c.fetchone()
        
        if not promo:
            return False, "❌ Промокод не найден"
        
        promo_id, amount, uses_left, expiry_date, is_active = promo
        
        # Проверяем активность
        if is_active != 1:
            return False, "❌ Промокод не активен"
        
        # Проверяем срок действия
        if expiry_date and datetime.now() > datetime.strptime(expiry_date, "%Y-%m-%d"):
            return False, "❌ Срок действия промокода истёк"
        
        # Проверяем количество использований
        if uses_left <= 0:
            return False, "❌ Промокод уже использован"
        
        # Проверяем, не использовал ли уже пользователь этот промокод
        c.execute("SELECT id FROM promocode_usage WHERE user_id = ? AND promocode_id = ?", 
                 (user_id, promo_id))
        if c.fetchone():
            return False, "❌ Вы уже использовали этот промокод"
        
        # Активируем промокод
        c.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE id = ?", (promo_id,))
        
        # Записываем использование
        c.execute("INSERT INTO promocode_usage (user_id, promocode_id) VALUES (?, ?)", 
                 (user_id, promo_id))
        
        # Начисляем коины
        update_balance(user_id, amount, "promo", f"Активация промокода: {code}")
        
        conn.commit()
        return True, f"✅ Промокод активирован! Получено: {amount} {CURRENCY_NAME}"
        
    except Exception as e:
        logger.error(f"Ошибка активации промокода: {e}")
        conn.rollback()
        return False, "❌ Ошибка активации промокода"
    finally:
        conn.close()

def check_subscription(user_id):
    """Проверка подписки на канал"""
    if not SUBSCRIPTION_REQUIRED:
        return True
    
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return True

# --- ПРОВЕРКА НОМЕРА ---
def get_phone_info(phone_number):
    """Получение расширенной информации о номере телефона"""
    try:
        # Нормализация номера
        phone_number = phone_number.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        if phone_number.startswith('8') and len(phone_number) == 11:
            phone_number = '+7' + phone_number[1:]
        elif phone_number.startswith('7') and len(phone_number) == 11:
            phone_number = '+7' + phone_number[1:]
        
        parsed_num = phonenumbers.parse(phone_number, None)
        
        if not phonenumbers.is_valid_number(parsed_num):
            return None
        
        # Базовая информация
        country_code = str(parsed_num.country_code)
        national_number = str(parsed_num.national_number)
        international = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        
        # Определение страны
        country = COUNTRY_NAMES.get(country_code, "Неизвестно")
        
        # Определение оператора
        operator = "Неизвестно"
        if country_code in WORLD_OPERATORS:
            for op, prefixes in WORLD_OPERATORS[country_code].items():
                for prefix in prefixes:
                    if national_number.startswith(prefix):
                        operator = op
                        break
                if operator != "Неизвестно":
                    break
        
        # Время
        time_zones = timezone.time_zones_for_number(parsed_num) or ["Неизвестно"]
        
        # Тип номера
        number_type = phonenumbers.number_type(parsed_num)
        type_names = {
            0: "📞 Стационарный",
            1: "📱 Мобильный", 
            2: "🆓 Бесплатный",
            3: "💎 Премиум",
            5: "🌐 VoIP",
            6: "👤 Персональный",
            7: "📟 Пейджер"
        }
        phone_type = type_names.get(number_type, "❓ Неизвестный")
        
        # Регион для России
        region = "Неизвестно"
        if country_code == '7' and len(national_number) >= 3:
            region_code = national_number[:3]
            region = RUSSIAN_REGIONS.get(region_code, "Неизвестный регион")
        
        return {
            "valid": True,
            "international": international,
            "national": phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.NATIONAL),
            "country": country,
            "country_code": country_code,
            "operator": operator,
            "region": region,
            "timezones": ", ".join(time_zones),
            "type": phone_type,
            "raw_number": national_number
        }
    except Exception as e:
        logger.error(f"Ошибка обработки номера {phone_number}: {e}")
        return None

# --- МЕНЮ ---
def create_main_menu(user_id):
    """Главное меню"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    balance = get_user_balance(user_id)
    
    buttons = [
        types.KeyboardButton("🔍 Проверить номер"),
        types.KeyboardButton("📧 Проверить email"),
        types.KeyboardButton(f"💰 Баланс: {balance}"),
        types.KeyboardButton("🎁 Бонусы"),
        types.KeyboardButton("💎 Премиум"),
        types.KeyboardButton("📊 Статистика"),
        types.KeyboardButton("🛠️ Инструменты"),
        types.KeyboardButton("ℹ️ Помощь")
    ]
    
    if is_admin(user_id):
        buttons.append(types.KeyboardButton("👑 Админ"))
    
    markup.add(*buttons)
    return markup

def create_bonus_menu():
    """Меню бонусов"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🎰 Ежедневный бонус"),
        types.KeyboardButton("🎫 Активировать промокод"),
        types.KeyboardButton("👥 Реферальная система"),
        types.KeyboardButton("⬅️ Назад")
    )
    return markup

def create_admin_menu():
    """Админ меню"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📊 Статистика бота"),
        types.KeyboardButton("👥 Управление пользователями"),
        types.KeyboardButton("💰 Выдать коины"),
        types.KeyboardButton("🎫 Создать промокод"),
        types.KeyboardButton("📋 Список промокодов"),
        types.KeyboardButton("🚫 Заблокировать"),
        types.KeyboardButton("🎁 Выдать премиум"),
        types.KeyboardButton("⚙️ Настройки"),
        types.KeyboardButton("⬅️ Главное меню")
    )
    return markup

def create_tools_menu():
    """Меню инструментов"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📱 QR код"),
        types.KeyboardButton("🔐 Хеширование"),
        types.KeyboardButton("🔒 Проверка пароля"),
        types.KeyboardButton("📄 Base64"),
        types.KeyboardButton("⬅️ Назад")
    )
    return markup

def create_back_button():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("⬅️ Назад"))
    return markup

# --- ОСНОВНЫЕ ОБРАБОТЧИКИ ---
@bot.message_handler(commands=['start'])
def start_command(message):
    """Команда /start"""
    user_id = message.from_user.id
    init_db()
    
    # Регистрируем пользователя
    conn = sqlite3.connect('osint.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not c.fetchone():
        referral_code = str(uuid.uuid4())[:8].upper()
        
        referred_by = None
        if len(message.text.split()) > 1:
            ref_code = message.text.split()[1]
            c.execute("SELECT user_id FROM users WHERE referral_code = ?", (ref_code,))
            ref_result = c.fetchone()
            if ref_result:
                referred_by = ref_result[0]
        
        c.execute("""INSERT INTO users 
                     (user_id, username, first_name, last_name, referral_code, referred_by, balance) 
                     VALUES (?, ?, ?, ?, ?, ?, 100)""",
                  (user_id, 
                   message.from_user.username,
                   message.from_user.first_name,
                   message.from_user.last_name,
                   referral_code,
                   referred_by))
        
        # Начисляем бонус рефереру
        if referred_by:
            update_balance(referred_by, REFERRAL_BONUS, "referral", f"Реферал: {user_id}")
    
    conn.commit()
    conn.close()
    
    # Проверяем подписку
    if not check_subscription(user_id):
        markup = types.InlineKeyboardMarkup()
        subscribe_btn = types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_LINK)
        check_btn = types.InlineKeyboardButton("✅ Проверить", callback_data="check_subscription")
        markup.add(subscribe_btn, check_btn)
        
        bot.send_message(
            message.chat.id,
            f"📢 *Для использования бота необходимо подписаться на наш канал*\n\n"
            f"После подписки нажмите кнопку '✅ Проверить'",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return
    
    welcome_text = (
        f"👋 Привет, *{message.from_user.first_name}*!\n\n"
        f"🕵️‍♂️ *OSINT Master Bot*\n\n"
        f"*Доступные функции:*\n"
        f"• 🔍 Проверка номеров телефонов\n"
        f"• 📧 Анализ email адресов\n"
        f"• 🛠️ Инструменты для работы\n"
        f"• 💰 Система коинов\n"
        f"• 🎁 Бонусы и промокоды\n\n"
        f"💰 *Ваш баланс:* {get_user_balance(user_id)} {CURRENCY_NAME}\n\n"
        f"Используйте кнопки ниже:"
    )
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=create_main_menu(user_id),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def check_subscription_callback(call):
    """Проверка подписки"""
    user_id = call.from_user.id
    
    if check_subscription(user_id):
        # Обновляем статус подписки
        conn = sqlite3.connect('osint.db')
        c = conn.cursor()
        c.execute("UPDATE users SET subscribed = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ *Вы успешно подписались!*\n\nТеперь вы можете пользоваться всеми функциями бота.",
            parse_mode="Markdown"
        )
        
        time.sleep(1)
        bot.send_message(
            call.message.chat.id,
            "Выберите действие:",
            reply_markup=create_main_menu(user_id)
        )
    else:
        bot.answer_callback_query(call.id, "❌ Вы еще не подписались на канал!")

# Проверка номера телефона
@bot.message_handler(func=lambda msg: msg.text == "🔍 Проверить номер")
def ask_phone_number(message):
    user_id = message.from_user.id
    
    # Проверяем баланс
    balance = get_user_balance(user_id)
    if balance < 1:
        bot.send_message(
            message.chat.id,
            f"❌ Недостаточно коинов!\n"
            f"💰 Ваш баланс: {balance} {CURRENCY_NAME}\n"
            f"💸 Стоимость проверки: 1 {CURRENCY_NAME}\n\n"
            f"🎁 Получите коины через меню 'Бонусы'",
            reply_markup=create_main_menu(user_id)
        )
        return
    
    msg = bot.send_message(
        message.chat.id,
        "📱 *Введите номер телефона:*\n\n"
        "Поддерживаемые форматы:\n"
        "• +79123456789\n" 
        "• 89123456789\n"
        "• +380441234567\n"
        "• +12345678901\n\n"
        "💡 *Стоимость:* 1 коин",
        reply_markup=create_back_button(),
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_phone_number)

def process_phone_number(message):
    if message.text == "⬅️ Назад":
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=create_main_menu(message.from_user.id))
        return
    
    user_id = message.from_user.id
    phone = message.text.strip()
    
    # Списываем коины
    update_balance(user_id, -1, "phone_check", f"Проверка номера: {phone}")
    
    # Получаем информацию
    info = get_phone_info(phone)
    
    if not info:
        bot.send_message(
            message.chat.id,
            "❌ Неверный номер или ошибка обработки.",
            reply_markup=create_main_menu(user_id)
        )
        return
    
    # Формируем ответ
    response = (
        f"📊 *Информация о номере:*\n\n"
        f"📱 *Номер:* `{info['international']}`\n"
        f"📍 *Страна:* {info['country']}\n"
        f"🏢 *Оператор:* {info['operator']}\n"
        f"🗺️ *Регион:* {info['region']}\n"
        f"🕒 *Часовой пояс:* {info['timezones']}\n"
        f"📞 *Тип:* {info['type']}\n\n"
        f"💰 *Потрачено:* 1 {CURRENCY_NAME}\n"
        f"💳 *Баланс:* {get_user_balance(user_id)} {CURRENCY_NAME}"
    )
    
    bot.send_message(
        message.chat.id,
        response,
        parse_mode="Markdown",
        reply_markup=create_main_menu(user_id)
    )

# Бонусы
@bot.message_handler(func=lambda msg: msg.text == "🎁 Бонусы")
def bonuses_menu(message):
    bot.send_message(
        message.chat.id,
        "🎁 *Система бонусов*\n\n"
        "Выберите действие:",
        reply_markup=create_bonus_menu(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "🎰 Ежедневный бонус")
def daily_bonus(message):
    user_id = message.from_user.id
    
    conn = sqlite3.connect('osint.db')
    c = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    c.execute("SELECT daily_bonus_claimed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if result and result[0] == today:
        bot.send_message(
            message.chat.id,
            "❌ Вы уже получали ежедневный бонус сегодня\n"
            "Приходите завтра!",
            reply_markup=create_bonus_menu()
        )
        conn.close()
        return
    
    bonus = random.randint(10, 50)
    update_balance(user_id, bonus, "daily_bonus", "Ежедневный бонус")
    
    c.execute("UPDATE users SET daily_bonus_claimed = ? WHERE user_id = ?", (today, user_id))
    conn.commit()
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"🎉 *Вы получили ежедневный бонус!*\n\n"
        f"💰 *Начислено:* {bonus} {CURRENCY_NAME}\n"
        f"📅 *До следующего бонуса:* завтра",
        parse_mode="Markdown",
        reply_markup=create_bonus_menu()
    )

@bot.message_handler(func=lambda msg: msg.text == "🎫 Активировать промокод")
def activate_promo_start(message):
    msg = bot.send_message(
        message.chat.id,
        "🎫 *Введите промокод:*\n\n"
        "Пример: ABC123DE",
        reply_markup=create_back_button(),
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, activate_promo_process)

def activate_promo_process(message):
    if message.text == "⬅️ Назад":
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=create_main_menu(message.from_user.id))
        return
    
    promo_code = message.text.strip().upper()
    user_id = message.from_user.id
    
    success, result_message = use_promo_code(user_id, promo_code)
    
    bot.send_message(
        message.chat.id,
        result_message,
        reply_markup=create_bonus_menu()
    )

# Админ панель
@bot.message_handler(func=lambda msg: msg.text == "👑 Админ" and is_admin(msg.from_user.id))
def admin_panel(message):
    bot.send_message(
        message.chat.id,
        "👑 *Админ панель*\n\n"
        "Выберите действие:",
        reply_markup=create_admin_menu(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "💰 Выдать коины" and is_admin(msg.from_user.id))
def give_coins_start(message):
    msg = bot.send_message(
        message.chat.id,
        "💰 *Выдача коинов*\n\n"
        "Введите ID пользователя и сумму через пробел:\n"
        "Пример: `123456789 100`",
        reply_markup=create_back_button(),
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, give_coins_process)

def give_coins_process(message):
    if message.text == "⬅️ Назад":
        bot.send_message(message.chat.id, "Админ панель:", reply_markup=create_admin_menu())
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ Неверный формат. Используйте: ID СУММА")
            return
        
        user_id = int(parts[0])
        amount = int(parts[1])
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть положительной")
            return
        
        success = update_balance(user_id, amount, "admin_gift", 
                                f"Выдано админом: {message.from_user.id}")
        
        if success:
            conn = sqlite3.connect('osint.db')
            c = conn.cursor()
            c.execute("SELECT username, first_name, balance FROM users WHERE user_id = ?", (user_id,))
            user_info = c.fetchone()
            conn.close()
            
            username = user_info[0] or "без username"
            first_name = user_info[1] or "Пользователь"
            new_balance = user_info[2]
            
            bot.send_message(
                message.chat.id,
                f"✅ *Коины успешно выданы!*\n\n"
                f"👤 *Пользователь:* {first_name} (@{username})\n"
                f"🆔 *ID:* {user_id}\n"
                f"💰 *Сумма:* {amount} {CURRENCY_NAME}\n"
                f"📊 *Новый баланс:* {new_balance} {CURRENCY_NAME}",
                parse_mode="Markdown",
                reply_markup=create_admin_menu()
            )
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при выдаче коинов")
            
    except ValueError:
        bot.send_message(message.chat.id, "❌ Ошибка в данных. Проверьте ID и сумму")
    except Exception as e:
        logger.error(f"Ошибка выдачи коинов: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda msg: msg.text == "🎫 Создать промокод" and is_admin(msg.from_user.id))
def create_promo_start(message):
    msg = bot.send_message(
        message.chat.id,
        "🎫 *Создание промокода*\n\n"
        "Введите данные в формате:\n"
        "`СУММА ИСПОЛЬЗОВАНИЯ ДНИ [описание]`\n\n"
        "Примеры:\n"
        "• `100 1 30 Новогодний промокод`\n"
        "• `500 10 7 Промоакция`",
        reply_markup=create_back_button(),
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, create_promo_process)

def create_promo_process(message):
    if message.text == "⬅️ Назад":
        bot.send_message(message.chat.id, "Админ панель:", reply_markup=create_admin_menu())
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ Неверный формат. Нужно минимум 3 параметра")
            return
        
        amount = int(parts[0])
        uses = int(parts[1])
        days = int(parts[2])
        description = " ".join(parts[3:]) if len(parts) > 3 else "Промокод от администратора"
        
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть положительной")
            return
        
        if uses <= 0:
            bot.send_message(message.chat.id, "❌ Количество использований должно быть положительным")
            return
        
        code = create_promo_code(
            amount=amount,
            uses_total=uses,
            expiry_days=days if days > 0 else None,
            description=description,
            created_by=message.from_user.id
        )
        
        if code:
            expiry_text = "без срока действия" if days == 0 else f"на {days} дней"
            
            bot.send_message(
                message.chat.id,
                f"✅ *Промокод создан!*\n\n"
                f"🎫 *Код:* `{code}`\n"
                f"💰 *Сумма:* {amount} {CURRENCY_NAME}\n"
                f"🔄 *Использований:* {uses}\n"
                f"📅 *Срок:* {expiry_text}\n"
                f"📝 *Описание:* {description}",
                parse_mode="Markdown",
                reply_markup=create_admin_menu()
            )
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при создании промокода")
            
    except ValueError:
        bot.send_message(message.chat.id, "❌ Ошибка в данных. Проверьте числа")
    except Exception as e:
        logger.error(f"Ошибка создания промокода: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda msg: msg.text == "📋 Список промокодов" and is_admin(msg.from_user.id))
def list_promocodes(message):
    conn = sqlite3.connect('osint.db')
    c = conn.cursor()
    
    c.execute("""SELECT code, amount, uses_total, uses_left, expiry_date, 
                        created_date, description, is_active 
                 FROM promocodes 
                 ORDER BY created_date DESC 
                 LIMIT 20""")
    
    promocodes = c.fetchall()
    conn.close()
    
    if not promocodes:
        bot.send_message(message.chat.id, "📭 Нет созданных промокодов")
        return
    
    text = "📋 *Список промокодов*\n\n"
    
    for promo in promocodes:
        code, amount, total, left, expiry, created, desc, active = promo
        
        status = "✅ Активен" if active == 1 else "❌ Неактивен"
        expiry_text = expiry if expiry else "∞"
        used = total - left
        
        text += (
            f"🎫 *{code}* ({status})\n"
            f"💰 {amount} коинов | 🔄 {used}/{total}\n"
            f"📅 Создан: {created}\n"
            f"📆 Действует до: {expiry_text}\n"
            f"📝 {desc}\n"
            f"{'-'*30}\n"
        )
    
    bot.send_message(
        message.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=create_admin_menu()
    )

# Навигация
@bot.message_handler(func=lambda msg: msg.text == "⬅️ Назад")
def back_to_main(message):
    bot.send_message(
        message.chat.id,
        "Главное меню:",
        reply_markup=create_main_menu(message.from_user.id)
    )

@bot.message_handler(func=lambda msg: msg.text == "⬅️ Главное меню" and is_admin(msg.from_user.id))
def admin_back_to_main(message):
    bot.send_message(
        message.chat.id,
        "Главное меню:",
        reply_markup=create_main_menu(message.from_user.id)
    )

# Запуск бота
if __name__ == "__main__":
    logger.info("🟢 Запуск бота...")
    init_db()
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        logger.error(f"❌ Ошибка при работе бота: {e}")
    finally:
        logger.info("🔴 Бот остановлен")