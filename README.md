# Packing List Summarization System

A full-stack application to extract and summarize data from packing lists using multimodal AI.

## Project Structure
- **/backend**: FastAPI server for processing PDF documents.
- **/frontend**: Vite + React + Tailwind CSS dashboard for interacting with extracted data.

---

## 🛠️ Getting Started

Follow the instructions below to set up and run both the backend and frontend.

### 1. Backend Setup (FastAPI)

Prerequisites: Python 3.10+

1.  **Navigate to the backend directory:**
    ```powershell
    cd backend
    ```
2.  **Environment Variables:**
    Copy `.env.example` to `.env` and add your OpenRouter API key:
    ```powershell
    copy .env.example .env
    # Edit .env and enter your OPENROUTER_API_KEY
    ```
3.  **Install dependencies:**
    ```powershell
    pip install -r requirements.txt
    ```
4.  **Run the server:**
    ```powershell
    python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
    ```
    *Alternatively, run the batch script:* `start_backend.bat`

    > [!TIP]
    > The API documentation is available at [http://localhost:8080/docs](http://localhost:8080/docs) when the server is running.

---

### 2. Frontend Setup (React/Vite)

Prerequisites: Node.js 18+

1.  **Navigate to the frontend directory:**
    ```powershell
    cd frontend
    ```
2.  **Install dependencies:**
    ```powershell
    npm install
    ```
3.  **Run the development server:**
    ```powershell
    npm run dev
    ```
    *Alternatively, run the batch script:* `start_frontend.bat`

    > [!IMPORTANT]
    > Ensure the backend is running on port 8080 before starting the frontend, as it communicates with the local API.

---

## 🚀 Usage

1. Open your browser and go to [http://localhost:5173](http://localhost:5173).
2. Upload a packing list PDF (scanned or digital).
3. Review and edit the extracted fields if necessary.
4. Export the results to an Excel file.

---

## 📄 Troubleshooting

- **PDF processing issues:** Ensure `poppler` is installed and in your PATH if you are processing scanned images.
- **AI Extraction errors:** Check your `.env` for a valid `OPENROUTER_API_KEY`.
- **Backend Connection:** Verify that `cors` is correctly configured in `backend/main.py` if the frontend cannot reach the API.
