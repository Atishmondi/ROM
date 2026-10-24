"""Start the browser upload app: .venv/bin/python app.py"""
import argparse
from rom.web import create_app

app = create_app()

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Upload a video and measure elbow movement in your browser.')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    import uvicorn
    uvicorn.run(app,host=args.host,port=args.port)
