import argparse,json,logging
from pathlib import Path
from falcon.config import load_settings
from falcon.data import Repository,Provider
from falcon.engines import Orchestrator
from falcon.reporting import Renderer
from falcon.line_client import LineClient

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--no-line",action="store_true"); ap.add_argument("--period",default="1y"); a=ap.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    s=load_settings(); data=Provider(Repository(s.database_path)).all(s.tickers,a.period)
    result=Orchestrator(s).run(data); card=Renderer().render(result); print(card)
    p=Path("reports"); p.mkdir(exist_ok=True)
    (p/"latest.txt").write_text(card,encoding="utf-8")
    (p/f"{result.generated_at.date()}.json").write_text(json.dumps(result.to_dict(),ensure_ascii=False,indent=2),encoding="utf-8")
    if s.line_enabled and not a.no_line:
        c=LineClient()
        if c.ready:c.push(card)
        else:logging.warning("LINE secrets missing; report only")
if __name__=="__main__":main()
