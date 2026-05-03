from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    phone_number: str       
    order_details: str      
    user_confirmed: bool    
    order_completed: bool   
    campaign_message: str   # <-- الإضافة الجديدة هنا