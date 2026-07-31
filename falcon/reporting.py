class Renderer:
    def render(self,r):
        x=["══════════════════════","Falcon Trading OS",r.generated_at.strftime("%Y-%m-%d %H:%M"),"",
           f"市場：{r.market.regime.value}｜分數 {r.market.score}｜風險 {r.market.risk.value}",
           f"資料可信度：{r.market.confidence}%",r.market.summary]
        for d in r.decisions:
            x += ["","━━━━━━━━━━━━━━",d.name,f"現價：{d.price}",f"Trade Phase：{d.phase.value}",
                  f"Action：{d.action.value}",f"進場成熟度：{d.entry}%",f"停利成熟度：{d.exit}%",
                  f"建議部位：{d.position}%",f"支撐／壓力：{d.support}／{d.resistance}",
                  f"失效價：{d.invalidation}",f"下一步：{d.next_action}",f"最大風險：{d.biggest_risk}"]
        x+=["","━━━━━━━━━━━━━━","沒有符合SOP，空手就是最好的交易。","══════════════════════"]
        return "\n".join(x)
