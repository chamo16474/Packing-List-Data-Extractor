# 🔧 Troubleshooting Guide

## ❌ Error: "NetworkError when attempting to fetch resource"

### **Cause:** Backend server is not running

The frontend is trying to connect to `http://localhost:8080` but nothing is listening on that port.

---

## ✅ **Solution: Start the Backend**

### **Method 1: Double-Click the Batch File (Easiest)**

1. Navigate to: `D:\BUDDHIMAL\antigravity\paking list summerization\backend\`
2. Double-click: **`start_backend.bat`**
3. Wait for: `INFO: Uvicorn running on http://0.0.0.0:8080`
4. Keep the window open!
5. Now try uploading PDF in frontend

---

### **Method 2: Manual Start**

**Terminal 1 (Backend):**
```bash
cd "D:\BUDDHIMAL\antigravity\paking list summerization\backend"
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

**Expected Output:**
```
INFO:     Will watch for changes in: D:\BUDDHIMAL\antigravity\paking list summerization\backend
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

---

## ✅ **Verify Backend is Running**

### **Test 1: Check Port**
```bash
netstat -ano | findstr :8080
```

**Expected:** You should see a line with `LISTENING`

---

### **Test 2: Health Check**
Open browser: `http://localhost:8080/health`

**Expected Response:**
```json
{"status": "ok", "version": "1.0.0"}
```

---

### **Test 3: API Docs**
Open browser: `http://localhost:8080/docs`

**Expected:** Swagger UI with API documentation

---

## 🔍 **Other Common Issues**

---

### **Error: "OPENROUTER_API_KEY not configured"**

**Cause:** API key not set in `.env` file

**Solution:**
1. Open `backend/.env`
2. Replace `your-openrouter-api-key-here` with your actual key
3. Restart backend

**Get API Key:** [https://openrouter.ai/keys](https://openrouter.ai/keys)

---

### **Error: "CORS policy blocked"**

**Cause:** Frontend and backend on different ports/origins

**Solution:**
- Backend should be on `http://localhost:8080`
- Frontend should be on `http://localhost:5173` (Vite default)
- CORS is already enabled in `backend/main.py`

If still issues, add to frontend `vite.config.ts`:
```typescript
server: {
  proxy: {
    '/upload': 'http://localhost:8080',
    '/result': 'http://localhost:8080',
    '/mapping': 'http://localhost:8080',
    '/output': 'http://localhost:8080',
  }
}
```

---

### **Error: "413 Request Entity Too Large"**

**Cause:** PDF file is too large

**Solution:**
1. Backend: Increase limit in `main.py`:
```python
app = FastAPI()
app.config.max_upload_size = 50 * 1024 * 1024  # 50MB
```

2. Or compress your PDF to < 10MB

---

### **Error: "429 Too Many Requests"**

**Cause:** API rate limit exceeded

**Solution:**
- **OpenRouter:** Wait 1 minute (60 req/min limit)
- **Gemini:** Wait 1 minute (15 req/min limit)
- Or switch to OpenRouter (higher limits)

---

### **Error: "ModuleNotFoundError: No module named 'xxx'"**

**Cause:** Missing Python dependencies

**Solution:**
```bash
cd "D:\BUDDHIMAL\antigravity\paking list summerization\backend"
pip install -r requirements.txt
```

---

### **Error: "npm ERR! code ENOENT"**

**Cause:** Missing Node.js dependencies

**Solution:**
```bash
cd "D:\BUDDHIMAL\antigravity\paking list summerization\frontend"
npm install
```

---

## 📊 **Startup Checklist**

### **Backend:**
- [ ] Python 3.10+ installed
- [ ] `.env` file exists with API keys
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Server running on port 8080
- [ ] Health check passes (`http://localhost:8080/health`)

### **Frontend:**
- [ ] Node.js 18+ installed
- [ ] Dependencies installed (`npm install`)
- [ ] Dev server running on port 5173
- [ ] Can access `http://localhost:5173`
- [ ] Console shows no CORS errors

---

## 🚀 **Quick Start Commands**

### **Start Everything from Scratch:**

**Terminal 1 - Backend:**
```bash
cd "D:\BUDDHIMAL\antigravity\paking list summerization\backend"

# Install dependencies (if first time)
pip install -r requirements.txt

# Start server
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

**Terminal 2 - Frontend:**
```bash
cd "D:\BUDDHIMAL\antigravity\paking list summerization\frontend"

# Install dependencies (if first time)
npm install

# Start dev server
npm run dev
```

**Browser:**
```
http://localhost:5173
```

---

## 📝 **Log Locations**

### **Backend Logs:**
- `backend/logs/errors.log` - Error logs
- `backend/logs/gemini_usage.log` - Gemini API calls
- Console output - Real-time logs

### **Frontend Logs:**
- Browser DevTools Console (F12)
- Terminal running `npm run dev`

---

## 🆘 **Still Having Issues?**

### **1. Check Python Version**
```bash
python --version
```
**Required:** Python 3.10 or higher

### **2. Check Node Version**
```bash
node --version
```
**Required:** Node.js 18 or higher

### **3. Restart Everything**
```bash
# Stop both servers (Ctrl+C)

# Restart backend
cd "D:\BUDDHIMAL\antigravity\paking list summerization\backend"
uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# In new terminal, restart frontend
cd "D:\BUDDHIMAL\antigravity\paking list summerization\frontend"
npm run dev
```

### **4. Check Firewall**
Windows Firewall might be blocking port 8080.

**Allow port:**
1. Windows Defender Firewall → Advanced Settings
2. Inbound Rules → New Rule
3. Port → TCP → 8080
4. Allow the connection

### **5. Check Antivirus**
Some antivirus software blocks localhost connections.

**Temporarily disable** and test, or add exception for Python/Node.js.

---

## 📞 **Need More Help?**

### **Collect This Information:**
1. **Backend logs:** Last 20 lines from console
2. **Frontend errors:** Browser console (F12)
3. **Error screenshot:** Full error message
4. **Steps to reproduce:** What you did before error

### **Then:**
- Check `backend/logs/errors.log`
- Check browser console (F12)
- Review this guide again
- Try the quick start commands above

---

## ✅ **Working Configuration Example**

**Backend running:**
```
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

**Frontend running:**
```
VITE v5.x.x  ready in xxx ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
```

**Browser:**
- URL: `http://localhost:5173`
- No console errors
- Can upload PDF successfully

---

**🎉 If everything is working, you should be able to upload PDFs and see extraction results!**
