import re

with open('dashboard/indicadores_senadores.html', encoding='utf-8') as f:
    c = f.read()

# Script CF
c = c.replace(
    '<script data-cfasync="false" src="/cdn-cgi/scripts/5c5dd728/cloudflare-static/email-decode.min.js"></script><script>',
    '<script>'
)

# Email 1 autor
c = re.sub(
    r'<a class="autor-mail" href="/cdn-cgi/l/email-protection#7f09[^"]*">.*?</a>',
    '<a class="autor-mail" href="mailto:vhmonte@retina.ar">\u2709\ufe0f vhmonte@retina.ar</a>',
    c
)

# Email 2 autor
c = re.sub(
    r'<a class="autor-mail" href="/cdn-cgi/l/email-protection#92ff[^"]*">.*?</a>',
    '<a class="autor-mail" href="mailto:monteverdevicente@hotmail.com">\u2709\ufe0f monteverdevicente@hotmail.com</a>',
    c
)

# Email donacion
c = re.sub(
    r'<a href="/cdn-cgi/l/email-protection#0f79[^"]*"[^>]*>.*?</a>',
    '<a href="mailto:vhmonte@retina.ar" style="color:#92400e;font-weight:700">vhmonte@retina.ar</a>',
    c
)

with open('dashboard/indicadores_senadores.html', 'w', encoding='utf-8') as f:
    f.write(c)

print('OK')
print('CF restantes:', c.count('__cf_email__'))