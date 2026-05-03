import sqlite3
import os

# تحديد المسار المطلق للداتا بيز عشان نضمن إنه مش بيكتب في فايل تاني
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'whatsapp_campaign.db')

def normalize_phone(phone):
    """دالة للتأكد من وجود علامة + في بداية الرقم لمطابقة الداتا بيز"""
    return phone if phone.startswith('+') else f'+{phone}'

def save_order_to_db(phone_number, order_details):
    """حفظ تفاصيل الأوردر في الداتا بيز"""
    db_phone = normalize_phone(phone_number)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO orders (phone_number, order_details)
            VALUES (?, ?)
        ''', (db_phone, order_details))
        conn.commit()
        return True
    except Exception as e:
        print(f"Database error: {e}")
        return False
    finally:
        conn.close()

def get_campaign_message(phone_number):
    """جلب أول رسالة اتبعتت للعميل عشان الأيجنت يفهم السياق"""
    db_phone = normalize_phone(phone_number)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT last_sent_message FROM contacts WHERE phone_number = ?", (db_phone,))
        result = cursor.fetchone()
        return result[0] if result and result[0] else "لا توجد رسالة حملة مسجلة."
    except Exception:
        return "لا توجد رسالة حملة مسجلة."
    finally:
        conn.close()