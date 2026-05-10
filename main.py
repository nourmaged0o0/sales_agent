import os
import httpx
import sys
import uvicorn
import subprocess  # ضفنا المكتبة دي عشان نرن الكامبين
from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv
from graph import app as agent_app
from tools import get_campaign_message
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from tools import DB_PATH


load_dotenv()



app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
META_URL = f"https://graph.facebook.com/v25.0/{META_PHONE_NUMBER_ID}/messages"

@app.put("/api/leads/{lead_id}")
async def update_lead(lead_id: int, request: Request):
    data = await request.json()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE contacts SET name=?, phone_number=?, context_or_interest=? WHERE id=?",
                       (data['name'], data['phone_number'], data['interest'], lead_id))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM contacts WHERE id=?", (lead_id,))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

@app.get("/api/orders")
def get_orders():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY id DESC")
    columns = [column[0] for column in cursor.description]
    orders = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return orders

@app.get("/api/stats")
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    stats = {}
    stats['total_leads'] = cursor.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    stats['reached'] = cursor.execute("SELECT COUNT(*) FROM contacts WHERE status = 'reached'").fetchone()[0]
    stats['orders'] = cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return stats

@app.get("/api/leads")
def get_leads():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts ORDER BY id DESC")
    columns = [column[0] for column in cursor.description]
    leads = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return leads

@app.post("/api/leads")
async def add_lead(request: Request):
    data = await request.json()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO contacts (name, phone_number, context_or_interest) VALUES (?, ?, ?)",
                       (data['name'], data['phone_number'], data['interest']))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

@app.post("/api/run-campaign")
def run_campaign_manual():
    try:
        subprocess.run([sys.executable, "campaign.py"], check=True)
        return {"status": "campaign started"}
    except:
        return {"status": "error"}


@app.get("/whatsapp")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == META_VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(status_code=403)

@app.post("/whatsapp")
async def receive_message(request: Request):
    body = await request.json()
    try:
        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        message = value["messages"][0]
                        sender_number = message["from"]
                        
                        if message.get("type") == "text":
                            user_text = message["text"]["body"]

                            config = {"configurable": {"thread_id": sender_number}}
                            
                            # هنجيب الرسالة اللي اتبعتت للعميل ده من الداتا بيز
                            campaign_msg = get_campaign_message(sender_number)
                            
                            # هنباصي الرسالة جوه الـ state 
                            input_state = {
                                "messages": [("user", user_text)], 
                                "phone_number": sender_number,
                                "campaign_message": campaign_msg
                            }
                            
                            output = agent_app.invoke(input_state, config)
                            
                            agent_messages = []
                            for msg in output["messages"]:
                                if hasattr(msg, "type") and msg.type in ["ai", "agent"]:
                                    agent_messages.append(msg.content)
                                elif isinstance(msg, tuple) and msg[0] in ["ai", "agent"]:
                                    agent_messages.append(msg[1])

                            response_text = agent_messages[-1] if agent_messages else "عفواً، ثواني..."
                            
                            # ======= الإضافة هنا للطباعة المنظمة في التيرمينال =======
                            print(f"👤 العميل ({sender_number}): {user_text}", flush=True)
                            print(f"🤖 الأيجنت: {response_text}", flush=True)
                            print("-" * 50, flush=True)
                            # =======================================================

                            await send_whatsapp_message(sender_number, response_text)
    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة الرسالة: {e}")

    return {"status": "success"}

async def send_whatsapp_message(to: str, text: str):
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    async with httpx.AsyncClient() as client:
        await client.post(META_URL, headers=headers, json=payload)

if __name__ == "__main__":
    # تشغيل ملف الكامبين الأول قبل ما السيرفر يقوم
    # print("🚀 جاري تشغيل حملة الواتساب أولاً (campaign.py)...")
    # try:
    #     subprocess.run([sys.executable, "campaign.py"], check=True)
    #     print("✅ تم الانتهاء من إرسال رسائل الحملة.")
    # except subprocess.CalledProcessError as e:
    #     print(f"❌ حصل خطأ أثناء تشغيل الحملة: {e}")
    # except FileNotFoundError:
    #     print("❌ ملف campaign.py غير موجود، تأكد من الاسم.")
        
    # تشغيل سيرفر FastAPI بعد انتهاء الحملة
    print("🌐 جاري تشغيل سيرفر FastAPI...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)