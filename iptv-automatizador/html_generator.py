"""Geração do output HTML com as credenciais."""

import os
import logging
from datetime import datetime
from typing import Dict
from config import OUTPUT_DIR, OUTPUT_FILE

logger = logging.getLogger(__name__)


def generate_output_html(data: Dict[str, str], output_path: str = None) -> str:
    """Gera ficheiro HTML com as credenciais formatadas.
    
    Args:
        data: Dicionário com credenciais (username, password, dns, epg, m3u, email_used)
        output_path: Caminho alternativo para o ficheiro
        
    Returns:
        str: Caminho do ficheiro gerado
    """
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    
    # Garantir que a pasta existe
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Extrair valores
    username = data.get('username', 'N/A')
    password = data.get('password', 'N/A')
    dns = data.get('dns', 'N/A')
    epg = data.get('epg', 'N/A')
    m3u = data.get('m3u', 'N/A')
    email_used = data.get('email_used', 'N/A')
    url = data.get('url', '')
    
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    html_content = f'''<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IPTV Fiesta - Credenciais Trial</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        
        .container {{
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
            max-width: 800px;
            width: 100%;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        
        .header h1 {{
            color: #333;
            font-size: 2em;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            color: #666;
            font-size: 0.9em;
        }}
        
        .timestamp {{
            text-align: center;
            color: #999;
            font-size: 0.85em;
            margin-bottom: 30px;
        }}
        
        .credentials-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }}
        
        .credentials-table th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }}
        
        .credentials-table td {{
            padding: 15px;
            border-bottom: 1px solid #eee;
        }}
        
        .credentials-table tr:hover {{
            background-color: #f8f9fa;
        }}
        
        .field-name {{
            font-weight: 600;
            color: #333;
            width: 30%;
        }}
        
        .field-value {{
            color: #555;
            font-family: 'Courier New', monospace;
            background: #f4f4f4;
            padding: 8px 12px;
            border-radius: 6px;
            word-break: break-all;
        }}
        
        .copy-btn {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85em;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .copy-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }}
        
        .copy-btn:active {{
            transform: translateY(0);
        }}
        
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #999;
            font-size: 0.8em;
        }}
        
        .success-badge {{
            display: inline-block;
            background: #28a745;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.85em;
            margin-bottom: 20px;
        }}
        
        .email-info {{
            background: #e3f2fd;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            border-left: 4px solid #2196f3;
        }}
        
        .email-info strong {{
            color: #1976d2;
        }}
        
        @media (max-width: 600px) {{
            .container {{
                padding: 20px;
            }}
            
            .header h1 {{
                font-size: 1.5em;
            }}
            
            .credentials-table th,
            .credentials-table td {{
                padding: 10px;
                font-size: 0.9em;
            }}
            
            .field-name {{
                width: 40%;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="success-badge">✓ Trial Gerado com Sucesso</span>
            <h1>IPTV Fiesta - Credenciais</h1>
            <p class="subtitle">48h de acesso grátis</p>
        </div>
        
        <div class="timestamp">Gerado em: {timestamp}</div>
        
        <div class="email-info">
            <strong>Email utilizado:</strong> {email_used}
        </div>
        
        <table class="credentials-table">
            <thead>
                <tr>
                    <th>Campo</th>
                    <th>Valor</th>
                    <th>Ação</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="field-name">Username</td>
                    <td class="field-value" id="username">{username}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('username')">Copiar</button></td>
                </tr>
                <tr>
                    <td class="field-name">Password</td>
                    <td class="field-value" id="password">{password}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('password')">Copiar</button></td>
                </tr>
                <tr>
                    <td class="field-name">DNS/Domain</td>
                    <td class="field-value" id="dns">{dns}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('dns')">Copiar</button></td>
                </tr>
                <tr>
                    <td class="field-name">EPG (TV Guide)</td>
                    <td class="field-value" id="epg">{epg}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('epg')">Copiar</button></td>
                </tr>
                <tr>
                    <td class="field-name">M3U Playlist</td>
                    <td class="field-value" id="m3u">{m3u}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('m3u')">Copiar</button></td>
                </tr>
            </tbody>
        </table>
        
        <div class="footer">
            <p>Automatizador IPTV Fiesta • Dados extraídos automaticamente</p>
            {f'<p><a href="{url}" target="_blank">Abrir página original</a></p>' if url else ''}
        </div>
    </div>
    
    <script>
        function copyToClipboard(elementId) {{
            const element = document.getElementById(elementId);
            const text = element.innerText;
            
            navigator.clipboard.writeText(text).then(function() {{
                // Feedback visual
                const btn = event.target;
                const originalText = btn.innerText;
                btn.innerText = '✓ Copiado!';
                btn.style.background = '#28a745';
                
                setTimeout(function() {{
                    btn.innerText = originalText;
                    btn.style.background = '';
                }}, 2000);
            }}).catch(function(err) {{
                console.error('Erro ao copiar:', err);
                alert('Erro ao copiar. Selecione manualmente e copie com Ctrl+C.');
            }});
        }}
    </script>
</body>
</html>'''
    
    # Guardar ficheiro
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"HTML gerado: {output_path}")
    return output_path
