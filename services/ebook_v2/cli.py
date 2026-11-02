"""Explicit isolated initialization, independent worker and loopback web server."""
import argparse
import logging
import os
from pathlib import Path
import time
from threading import Event,Thread
import uuid


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("init","worker","serve"))
    parser.add_argument("--data",required=True,help="Separate Book Studio data directory")
    parser.add_argument("--once",action="store_true")
    parser.add_argument("--interval",type=float,default=1)
    args=parser.parse_args()
    if not .1<=args.interval<=30:parser.error("Interval must be between .1 and 30 seconds")
    data=Path(args.data).resolve();data.mkdir(parents=True,exist_ok=True)
    os.environ["FACTORY_DB_PATH"]=str(data/"studio.sqlite")
    os.environ["FACTORY_DB_BACKEND"]="sqlite";os.environ["DATABASE_URL"]=""
    from .books import Books,Conflict
    books=Books(data/"studio.sqlite",data/"objects");books.initialize()
    if args.action=="init":
        print("Separate Book Studio tables initialized")
    elif args.action=="serve":
        from .web import create_app
        create_app(books).run(host="127.0.0.1",port=5088,threaded=True,use_reloader=False)
    else:
        stopped=Event();worker_id=uuid.uuid4().hex
        capabilities={"local_text":False}
        def heartbeat():
            while not stopped.is_set():
                try:
                    from .local_text import ready
                    books.record_worker(worker_id,False)
                    capabilities["local_text"]=ready()
                    books.record_worker(worker_id,capabilities["local_text"])
                except Exception:logging.exception("Book Studio worker heartbeat failed")
                stopped.wait(3)
        monitor=Thread(target=heartbeat,daemon=True);monitor.start()
        try:
            while True:
                for row in books.pending():
                    if row.get("source")=="ollama" and not capabilities["local_text"]:continue
                    try:books.advance(row["owner"],row["id"])
                    except Conflict:pass
                    except Exception:logging.exception("Book Studio work needs attention")
                if args.once:break
                stopped.wait(args.interval)
        finally:
            stopped.set();monitor.join(4)


if __name__=="__main__":main()
