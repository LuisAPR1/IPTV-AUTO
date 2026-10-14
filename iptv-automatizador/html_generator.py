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
    <title>IPTV Access Portal — Credenciais de Teste</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, system-ui, sans-serif;
            background-color: #090a0f;
            color: #f4f4f5;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 24px 16px;
            line-height: 1.5;
        }}
        
        .container {{
            background: #111217;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 20px;
            box-shadow: 0 16px 40px -8px rgba(0, 0, 0, 0.6), inset 0 1px 0 0 rgba(255, 255, 255, 0.05);
            padding: 36px;
            max-width: 760px;
            width: 100%;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 24px;
        }}
        
        .success-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(16, 185, 129, 0.12);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.25);
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 14px;
        }}
        
        .header h1 {{
            color: #ffffff;
            font-size: 1.5em;
            font-weight: 600;
            letter-spacing: -0.02em;
            margin-bottom: 6px;
        }}
        
        .header .subtitle {{
            color: #a1a1aa;
            font-size: 0.9em;
        }}
        
        .timestamp {{
            text-align: center;
            color: #71717a;
            font-size: 0.8em;
            margin-bottom: 24px;
        }}
        
        .email-info {{
            background: #0d0e13;
            border: 1px solid rgba(255, 255, 255, 0.06);
            padding: 12px 16px;
            border-radius: 12px;
            margin-bottom: 24px;
            font-size: 0.85em;
            color: #a1a1aa;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
        }}
        
        .email-info strong {{
            color: #e4e4e7;
            font-weight: 500;
        }}
        
        .credentials-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0 8px;
            margin-bottom: 24px;
        }}
        
        .credentials-table th {{
            color: #71717a;
            padding: 8px 14px;
            text-align: left;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        .credentials-table tr.row-item {{
            background: #0d0e13;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 10px;
        }}
        
        .credentials-table td {{
            padding: 12px 14px;
            vertical-align: middle;
        }}
        
        .credentials-table td:first-child {{
            border-top-left-radius: 10px;
            border-bottom-left-radius: 10px;
        }}
        
        .credentials-table td:last-child {{
            border-top-right-radius: 10px;
            border-bottom-right-radius: 10px;
            text-align: right;
        }}
        
        .field-name {{
            font-weight: 500;
            color: #d4d4d8;
            font-size: 0.85em;
            width: 25%;
            white-space: nowrap;
        }}
        
        .field-value {{
            color: #f4f4f5;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.85em;
            word-break: break-all;
            user-select: all;
        }}
        
        .copy-btn {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #d4d4d8;
            padding: 6px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.8em;
            font-weight: 500;
            transition: all 0.15s ease;
            white-space: nowrap;
        }}
        
        .copy-btn:hover {{
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
            color: #ffffff;
        }}
        
        .copy-btn:active {{
            transform: scale(0.96);
        }}
        
        :focus-visible {{
            outline: 2px solid #a1a1aa;
            outline-offset: 2px;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 24px;
            padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            color: #71717a;
            font-size: 0.8em;
        }}
        
        .footer a {{
            color: #a1a1aa;
            text-decoration: underline;
            text-underline-offset: 3px;
        }}
        .footer a:hover {{
            color: #ffffff;
        }}
        
        @media (max-width: 600px) {{
            .container {{
                padding: 20px 16px;
            }}
            
            .header h1 {{
                font-size: 1.25em;
            }}
            
            .credentials-table th {{
                display: none;
            }}
            
            .credentials-table, .credentials-table tbody, .credentials-table tr.row-item {{
                display: block;
                width: 100%;
            }}
            
            .credentials-table tr.row-item {{
                margin-bottom: 10px;
                padding: 12px;
            }}
            
            .credentials-table td {{
                display: block;
                padding: 4px 0;
                width: 100% !important;
                text-align: left !important;
            }}
            
            .field-value {{
                margin: 6px 0;
            }}
            
            .copy-btn {{
                width: 100%;
                padding: 8px;
                margin-top: 6px;
            }}
        }}
        
        @media (prefers-reduced-motion: reduce) {{
            *, ::before, ::after {{
                animation-duration: 0.01ms !important;
                transition-duration: 0.01ms !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="success-badge">✓ Sessão Ativa • 48 Horas</span>
            <h1>IPTV Access Portal</h1>
            <p class="subtitle">Credenciais de teste provisionadas</p>
        </div>
        
        <div class="timestamp">Gerado a: {timestamp}</div>
        
        <div class="email-info">
            <span><strong>Email de verificação:</strong></span>
            <span style="font-family: ui-monospace, monospace; color: #d4d4d8;">{email_used}</span>
        </div>
        
        <table class="credentials-table">
            <thead>
                <tr>
                    <th>Parâmetro</th>
                    <th>Valor</th>
                    <th style="text-align: right;">Ação</th>
                </tr>
            </thead>
            <tbody>
                <tr class="row-item">
                    <td class="field-name">Username</td>
                    <td class="field-value" id="username">{username}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('username', this)">Copiar</button></td>
                </tr>
                <tr class="row-item">
                    <td class="field-name">Password</td>
                    <td class="field-value" id="password">{password}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('password', this)">Copiar</button></td>
                </tr>
                <tr class="row-item">
                    <td class="field-name">DNS / Host</td>
                    <td class="field-value" id="dns">{dns}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('dns', this)">Copiar</button></td>
                </tr>
                <tr class="row-item">
                    <td class="field-name">EPG (Guia)</td>
                    <td class="field-value" id="epg">{epg}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('epg', this)">Copiar</button></td>
                </tr>
                <tr class="row-item">
                    <td class="field-name">Playlist M3U</td>
                    <td class="field-value" id="m3u">{m3u}</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('m3u', this)">Copiar</button></td>
                </tr>
            </tbody>
        </table>
        
        <div class="footer">
            <p>IPTV Access Portal • Provisionamento Seguro</p>
            {f'<p style="margin-top: 6px;"><a href="{url}" target="_blank" rel="noopener">Página original do serviço</a></p>' if url else ''}
        </div>
    </div>
    
    <script>
        function copyToClipboard(elementId, btn) {{
            const element = document.getElementById(elementId);
            const text = element.innerText;
            
            navigator.clipboard.writeText(text).then(function() {{
                const originalText = btn.innerText;
                btn.innerText = '✓ Copiado';
                btn.style.color = '#34d399';
                btn.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                
                setTimeout(function() {{
                    btn.innerText = originalText;
                    btn.style.color = '';
                    btn.style.borderColor = '';
                }}, 2000);
            }}).catch(function(err) {{
                alert('Erro ao copiar. Seleciona manualmente.');
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
