import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from state import AgentState
from tools import save_order_to_db

load_dotenv()

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

class ExtractedData(BaseModel):
    has_order: str = Field(description="اكتب 'true' فقط إذا ذكر العميل خدمة محددة أو طلب شراء واضح يريد تنفيذه. الأسئلة والاستفسارات ليست طلبات. وإلا 'false'")
    order_details: str = Field(description="ما هو الطلب الذي يريده العميل باختصار؟ اتركها فارغة إذا كان مجرد سؤال أو استفسار عن رسالة سابقة.", default="")
    is_confirming: str = Field(description="اكتب 'true' إذا وافق العميل بوضوح على تأكيد الطلب. وإلا 'false'")

structured_llm = llm.with_structured_output(ExtractedData)

def extract_node(state: AgentState):
    history_text = ""
    for msg in state["messages"][-5:]:
        role = "العميل" if (hasattr(msg, "type") and msg.type in ['human', 'user']) or (isinstance(msg, tuple) and msg[0] in ['human', 'user']) else "الأيجنت"
        content = msg.content if hasattr(msg, "content") else msg[1]
        history_text += f"{role}: {content}\n"
    
    prompt = f"""
    أنت محلل بيانات دقيق. استخرج المعلومات من المحادثة:
    {history_text}
    
    تحذير هام: إذا كان العميل يسأل عن رسالة سابقة، أو يستفسر عن كيفية العمل، أو يقول "ازاي" فهذا *ليس* طلبًا (Order).
    الطلب يُحسب فقط عندما يقرر العميل بشكل واضح أنه يريد شراء خدمة معينة.
    
    1. هل ذكر العميل تفاصيل خدمة أو أوردر يريد تنفيذه بشكل قاطع؟
    2. هل أكد العميل الأوردر بعد ما سأله الأيجنت عن التأكيد؟
    """
    extraction = structured_llm.invoke(prompt)
    
    updates = {}
    if extraction.has_order.lower() == 'true' and extraction.order_details:
        updates["order_details"] = extraction.order_details
        updates["user_confirmed"] = False 
        
    if extraction.is_confirming.lower() == 'true':
        updates["user_confirmed"] = True
        
    return updates

def draft_reply_node(state: AgentState):
    order_details = state.get("order_details", "")
    confirmed = state.get("user_confirmed", False)
    completed = state.get("order_completed", False)
    campaign_msg = state.get("campaign_message", "")
    
    # حولنا التعليمات لـ System Prompt
    system_prompt = f"""
    أنت مساعد مبيعات مصري ذكي وودود. تحدث باللهجة العامية المصرية الطبيعية.
    هدفك هو مساعدة العميل، الرد على استفساراته، ثم توجيهه بلباقة لتحديد طلبه/الأوردر الخاص به وتأكيده.

    معلومة هامة جداً عن سياق المحادثة:
    الرسالة التسويقية التي بدأنا بها المحادثة مع العميل هي:
    "{campaign_msg}"
    (لو العميل سألك عن اللي قلته أو استفسر عن الرسالة دي، اشرحله بوضوح ولطافة بناءً عليها).

    حالة الطلب:
    - تفاصيل الطلب الحالية: {order_details if order_details else 'لم يحدد بعد'}
    - هل العميل أكد الطلب؟: {confirmed}
    - هل تم تسجيل الطلب في السيستم؟: {completed}

    قواعد الرد:
    1. لو (completed == True): اشكر العميل وقوله إن الأوردر اتسجل بنجاح وهنتواصل معاه.
    2. لو العميل بيستفسر عن رسالتنا أو بيتكلم بشكل عام: تفاعل مع كلامه بشكل طبيعي جداً وجاوب على سؤاله الأول، وبعدين بلطافة اعرض عليه خدماتنا.
    3. لو (حدد الطلب) ولكن (لم يؤكد بعد): قوله "تمام يا فندم، عشان أأكد معاك، طلبك هو: {order_details} .. أأكد الأوردر على كده؟".
    
    اكتب الرد الموجه للعميل فوراً وبدون مقدمات.
    """
    
    # هنا السر: بنباصي للـ LLM التعليمات + تاريخ المحادثة كله عشان يفهم العميل بيقول إيه
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    
    response = llm.invoke(messages)
    return {"messages": [("ai", response.content)]}

def execute_node(state: AgentState):
    phone = state.get("phone_number")
    order_details = state.get("order_details")
    
    success = save_order_to_db(phone, order_details)
    
    if success:
        msg = "تم تأكيد وتسجيل أوردرك بنجاح يا فندم! 🎉\nفريقنا هيتواصل معاك قريب جداً للتنفيذ. يومك جميل!"
        return {"messages": [("ai", msg)], "order_completed": True}
    else:
        return {"messages": [("ai", "معلش حصلت مشكلة تقنية وإحنا بنسجل الأوردر، ممكن نجرب نأكده تاني؟")]}

def router(state: AgentState):
    if state.get("order_completed"): return "draft_reply"
    
    order_details = state.get("order_details")
    confirmed = state.get("user_confirmed", False)
    
    if order_details and confirmed:
        return "execute"
        
    return "draft_reply"

workflow = StateGraph(AgentState)
workflow.add_node("extract", extract_node)
workflow.add_node("draft_reply", draft_reply_node)
workflow.add_node("execute", execute_node)

workflow.set_entry_point("extract")
workflow.add_conditional_edges("extract", router)
workflow.add_edge("draft_reply", END)
workflow.add_edge("execute", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)