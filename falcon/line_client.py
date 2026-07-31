import os,requests
class LineClient:
    URL="https://api.line.me/v2/bot/message/push"
    def __init__(self,token=None,user=None):
        self.token=token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN",""); self.user=user or os.getenv("LINE_USER_ID","")
    @property
    def ready(self): return bool(self.token and self.user)
    def push(self,text):
        if not self.ready: raise RuntimeError("LINE secrets missing")
        r=requests.post(self.URL,headers={"Authorization":f"Bearer {self.token}","Content-Type":"application/json"},
                        json={"to":self.user,"messages":[{"type":"text","text":text[:5000]}]},timeout=20)
        r.raise_for_status()
