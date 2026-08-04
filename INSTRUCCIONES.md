# 🔧 Fix Railway — Monitor Legislativo Senado

## ¿Por qué fallaba?

Railway mostraba el JSON raíz (`{"proyecto":...}`) en vez del dashboard porque:

1. **`/` no redirigía** al dashboard — respondía JSON directo
2. **`data/` no existía** en el repo → `StaticFiles` y CSVs fallaban
3. **Sin `DATABASE_URL`** → el lifespan podía crashear el boot

## Archivos a reemplazar en el repo

```
monitor_legistativo_senadores/
├── api/
│   └── run_senado.py        ← REEMPLAZAR (fix raíz + robustez sin DB)
├── dashboard/
│   ├── senado.html          ← REEMPLAZAR (con fallback datos embebidos)
│   └── indicadores.html     ← REEMPLAZAR (nueva versión completa)
├── data/
│   └── .gitkeep             ← AGREGAR (carpeta vacía para Railway)
└── railway.toml             ← REEMPLAZAR (healthcheckTimeout 30→60)
```

## Pasos

```bash
# 1. Clonar / abrir el repo
git clone https://github.com/Viny2030/monitor_legistativo_senadores
cd monitor_legistativo_senadores

# 2. Copiar los archivos de esta carpeta fix_railway/
cp fix_railway/api/run_senado.py api/run_senado.py
cp fix_railway/dashboard/senado.html dashboard/senado.html
cp fix_railway/dashboard/indicadores.html dashboard/indicadores.html
cp fix_railway/data/.gitkeep data/.gitkeep
cp fix_railway/railway.toml railway.toml

# 3. Commitear y pushear
git add api/run_senado.py dashboard/ data/.gitkeep railway.toml
git commit -m "fix: redirigir / al dashboard, robustecer boot sin DB"
git push origin main
```

## Resultado esperado

- `https://monitorlegistativosenadores-production.up.railway.app/` → redirige a `/dashboard/senado.html`
- `/salud` → `{"status":"ok", "dashboard":true, ...}` ← healthcheck pasa
- Si no hay DB ni CSV → el dashboard carga igual con datos embebidos de fallback
