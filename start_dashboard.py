import http.server
import socketserver
import webbrowser
import os
import threading
import subprocess
import time
import urllib.request
import atexit

PORT = 8000
API_PORT = 8001
DIRECTORY = "."
api_process = None

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def log_message(self, format, *args):
        # Silenciar los logs del servidor para no ensuciar la terminal
        pass

def start_server():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"-> Servidor montado en el puerto {PORT}")
        print("-> Cierra esta ventana o presiona Ctrl+C para apagar el servidor.")
        httpd.serve_forever()

def is_api_alive():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{API_PORT}/docs", timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False

def start_api_if_needed():
    global api_process
    if is_api_alive():
        print(f"-> API ya activa en puerto {API_PORT}")
        return

    print(f"-> Iniciando API de análisis en puerto {API_PORT}...")
    api_process = subprocess.Popen(
        ["python", "-m", "uvicorn", "api_sarcasmo:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    for _ in range(20):
        if is_api_alive():
            print("-> API lista.")
            return
        time.sleep(0.25)

    print("[!] La API no respondió a tiempo. Revisa dependencias o conflictos de puerto.")

def shutdown_api():
    global api_process
    if api_process and api_process.poll() is None:
        api_process.terminate()
        print("-> API detenida.")

if __name__ == "__main__":
    print("Iniciando servidor de Dashboard...")
    atexit.register(shutdown_api)
    start_api_if_needed()
    
    # Iniciar servidor en segundo plano
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Abrir archivo index.html relativo al servidor
    dashboard_url = f"http://localhost:{PORT}/dashboard/index.html"
    print(f"Abriendo {dashboard_url} en tu navegador...")
    webbrowser.open(dashboard_url)
    
    try:
        # Mantener el hilo principal vivo
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nApagando servidor...")
