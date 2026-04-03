import requests
import time
import json
import logging
import uuid
import sys

try:
    from reportlab.pdfgen import canvas
except ImportError:
    print("Installing reportlab and sseclient-py...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "reportlab", "sseclient-py"])
    from reportlab.pdfgen import canvas
    
import sseclient

def test_flow():
    url = "http://localhost:8080/upload"
    filepath = "test_doc.pdf"

    print("Generating dummy PDF...")
    c = canvas.Canvas(filepath)
    c.drawString(100, 750, "Client PO: 12345")
    c.drawString(100, 730, "Style: SHIRT001")
    c.drawString(100, 710, "PO Number: PO999")
    c.save()

    print("Uploading...")
    with open(filepath, "rb") as f:
        resp = requests.post(url, files={"file": (filepath, f, "application/pdf")}, data={"supplier_name": "guston"})

    if resp.status_code != 200:
        print("Upload failed!", resp.status_code, resp.text)
        return

    job_id = resp.json().get("job_id")
    print(f"job_id: {job_id}")

    print("Streaming logs...")
    try:
        response = requests.get(f"http://localhost:8080/stream/{job_id}", stream=True)
        client = sseclient.SSEClient(response)
        for event in client.events():
            print("EVENT:", event.data)
            if event.data == "DONE":
                break
    except Exception as e:
        print("SSE Error:", e)
        
    print("Fetching result...")
    res = requests.get(f"http://localhost:8080/result/{job_id}")
    if res.status_code == 200:
        print("RESULT:")
        print(json.dumps(res.json(), indent=2))
    else:
        print("Failed to get result:", res.status_code, res.text)

if __name__ == "__main__":
    test_flow()
