# RealTimeBus
My own personal use of real-time public transport

```bash
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &
```

```bash
ps aux | grep uvicorn
```

```bash
kill -9 <PID>
```

```bash
vim /etc/nginx/conf.d/bus.ggbor.com.conf
```