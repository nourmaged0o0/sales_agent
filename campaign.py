import os
import sqlite3
import requests
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

def get_pending_leads():
    conn = sqlite3.connect('whatsapp_campaign.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, phone_number, context_or_interest FROM contacts WHERE status = 'pending'")
    leads = cursor.fetchall()
    conn.close()
    return [{"name": row[0], "phone": row[1], "interest": row[2]} for row in leads]

def check_interest_cache(interest):
    conn = sqlite3.connect('whatsapp_campaign.db')
    cursor = conn.cursor()
    cursor.execute("SELECT template FROM message_cache WHERE interest = ?", (interest,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def save_interest_cache(interest, template):
    conn = sqlite3.connect('whatsapp_campaign.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO message_cache (interest, template) VALUES (?, ?)", (interest, template))
    conn.commit()
    conn.close()

def send_whatsapp_message(phone, message_in_arabic):
    PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
    ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    formatted_phone = phone.replace("+", "")
    payload = {
        "messaging_product": "whatsapp",
        "to": formatted_phone,
        "type": "text",
        "text": {"body": message_in_arabic}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        return response.status_code in [200, 201]
    except:
        return False

# تم التعديل هنا لاستقبال وحفظ الرسالة
def update_lead_status(phone, status, sent_message=""):
    conn = sqlite3.connect('whatsapp_campaign.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE contacts SET status = ?, last_sent_message = ? WHERE phone_number = ?", (status, sent_message, phone))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.4)
    leads = get_pending_leads()
    
    for lead in leads:
        name = lead["name"]
        phone = lead["phone"]
        interest = lead["interest"]
        template = check_interest_cache(interest)
        
        if template:
            print(f"Cache HIT: Skipping LLM for '{interest}'")
            final_message = template.replace("[NAME]", name)
        else:
            print(f"Cache MISS: Calling LLM for '{interest}'")
            prompt = f"""اكتب رسالة واتساب تسويقية قصيرة جدا ومباشرة باللهجة المصرية لشخص مهتم بـ '{interest}'.
            يجب أن تحتوي الرسالة على كلمة [NAME] كعنصر نائب للاسم. اسأله في النهاية سؤال يخليه يرد علينا."""
            
            response = llm.invoke(prompt)
            template = response.content.strip()
            save_interest_cache(interest, template)
            final_message = template.replace("[NAME]", name)
            
        success = send_whatsapp_message(phone, final_message)
        status = "reached" if success else "couldn't reach"
        
        # تم التعديل هنا لتمرير الرسالة النهائية عشان تتحفظ في الداتا بيز
        update_lead_status(phone, status, final_message)