"""Serviço de email usando Gmail pessoal com plus-addressing."""

import time
import re
import logging
import random
import string
import imaplib
import email
from email.header import decode_header
from typing import Optional, Dict, Any, List
from config import EMAIL_TIMEOUT, EMAIL_POLL_INTERVAL

logger = logging.getLogger(__name__)


class PersonalGmailService:
    """Serviço usando Gmail pessoal com plus-addressing.
    
    Gera emails como: tua_conta+abc123@gmail.com
    Todos os emails chegam à caixa de entrada principal.
    
    Requer:
    - Gmail base (ex: tua_conta@gmail.com)
    - App Password do Gmail (não a password normal!)
    
    Como criar App Password:
    1. Ativar 2FA na conta Google
    2. Ir a: https://myaccount.google.com/apppasswords
    3. Gerar password para "Mail"
    """
    
    def __init__(self, gmail_account: str, app_password: str):
        """
        Args:
            gmail_account: Email base (ex: "tua_conta@gmail.com")
            app_password: App Password do Gmail (16 caracteres)
        """
        self.gmail_account = gmail_account.strip() if gmail_account else ""
        self.app_password = app_password.replace(" ", "").strip() if app_password else ""
        self.email: Optional[str] = None
        self.generated_suffix: Optional[str] = None
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993
    
    def create_inbox(self) -> str:
        """Gera email com plus-addressing aleatório."""
        self.generated_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        
        local_part = self.gmail_account.split('@')[0]
        domain = self.gmail_account.split('@')[1]
        
        self.email = f"{local_part}+{self.generated_suffix}@{domain}"
        
        logger.info(f"✓ Gmail gerado: {self.email}")
        return self.email
    
    def check_messages(self) -> List[Dict]:
        """Verifica mensagens na caixa de entrada via IMAP."""
        if not self.generated_suffix:
            return []
        
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port, timeout=15)
            mail.login(self.gmail_account, self.app_password)
            mail.select("inbox")
            
            # Buscar mensagens récentas
            status, messages = mail.search(None, "ALL")
            
            if status != "OK" or not messages[0]:
                mail.logout()
                return []
            
            email_ids = messages[0].split()
            # Verificar as ultimas 10 mensagens
            recent_ids = email_ids[-10:]
            result = []
            
            for email_id in recent_ids:
                status, msg_data = mail.fetch(email_id, "(BODY.PEEK[])")
                
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                
                msg = email.message_from_bytes(msg_data[0][1])
                to_header = msg.get("To", "")
                
                if self.generated_suffix and f"+{self.generated_suffix}" in to_header:
                    subject = self._decode_header(msg.get("Subject", ""))
                    from_addr = self._decode_header(msg.get("From", ""))
                    content = self._extract_content(msg)
                    
                    result.append({
                        "id": email_id.decode(),
                        "from": from_addr,
                        "to": to_header,
                        "subject": subject,
                        "content": content,
                        "message": msg
                    })
            
            mail.logout()
            return result
            
        except imaplib.IMAP4.error as e:
            err_str = str(e)
            if "AUTHENTICATIONFAILED" in err_str or "Invalid credentials" in err_str:
                logger.error(f"❌ Erro de Autenticação no Gmail ({self.gmail_account}): Palavra-passe de aplicação rejeitada.")
                logger.error("👉 Como resolver:")
                logger.error("  1. Verifica se a variável GMAIL_APP_PASSWORD no Render contém a Palavra-passe de Aplicação de 16 letras (e NÃO a password normal da conta Google).")
                logger.error("  2. Gera uma nova em: https://myaccount.google.com/apppasswords")
                logger.error("  3. Confirma se o IMAP está ATIVO em: Gmail -> Definições -> Encaminhamento e POP/IMAP -> Ativar IMAP.")
            else:
                logger.warning(f"Erro IMAP: {e}")
            return []
        except Exception as e:
            logger.warning(f"Erro IMAP: {e}")
            return []
    
    def _decode_header(self, header: str) -> str:
        """Descodifica header de email."""
        decoded = decode_header(header)
        result = ""
        for part, charset in decoded:
            if isinstance(part, bytes):
                result += part.decode(charset or "utf-8", errors="ignore")
            else:
                result += part
        return result
    
    def _extract_content(self, msg) -> str:
        """Extrai conteúdo texto do email."""
        content = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ["text/plain", "text/html"]:
                    try:
                        content += "\n" + part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    except:
                        pass
        else:
            try:
                content = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            except:
                pass
        
        return content
    
    def extract_verification_code(self, content: str) -> Optional[str]:
        """Extrai código de verificação (numérico ou alfanumérico)."""
        patterns = [
            r'Verification Code is\s*(?:<strong>)?([A-Z0-9]{6,14})(?:</strong>)?',
            r'code[:\s]+<strong>?([A-Z0-9]{6,14})</strong>?',
            r'código[:\s]+<strong>?([A-Z0-9]{6,14})</strong>?',
            r'verification[:\s]+<strong>?([A-Z0-9]{6,14})</strong>?',
            r'confirmation[:\s]+<strong>?([A-Z0-9]{6,14})</strong>?',
            r'\b([A-Z0-9]{8,12})\b',
            r'\b(\d{4,6})\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def get_verification_code(self, timeout: int = EMAIL_TIMEOUT) -> Optional[str]:
        """Aguarda e extrai código de verificação."""
        logger.info(f"Aguardando email em {self.gmail_account}...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            messages = self.check_messages()
            
            for msg in messages:
                content = msg.get("content", "")
                subject = msg.get("subject", "")
                
                code = self.extract_verification_code(content)
                if not code:
                    code = self.extract_verification_code(subject)
                
                if code:
                    logger.info(f"✓ Código encontrado: {code}")
                    return code
            
            time.sleep(EMAIL_POLL_INTERVAL)
        
        logger.error("Timeout aguardando email")
        return None
    
    def cleanup(self):
        """Nada a limpar."""
        pass


class TempMailService:
    """Serviço de email temporário usando Gmail pessoal."""
    
    def __init__(self, personal_gmail: Optional[str] = None, app_password: Optional[str] = None):
        """
        Args:
            personal_gmail: Email Gmail pessoal
            app_password: App Password do Gmail (16 caracteres)
        """
        self.personal_gmail = personal_gmail
        self.app_password = app_password
        self.backend: Optional[str] = None
        self.personal_service: Optional[PersonalGmailService] = None
        self.email: Optional[str] = None
    
    def create_inbox(self) -> str:
        """Cria inbox usando Gmail pessoal."""
        if not self.personal_gmail or not self.app_password:
            raise ValueError("Gmail pessoal não configurado. Verifica PERSONAL_GMAIL e GMAIL_APP_PASSWORD no .env")
        
        logger.info("A usar Gmail pessoal com plus-addressing...")
        self.personal_service = PersonalGmailService(
            self.personal_gmail, 
            self.app_password
        )
        email = self.personal_service.create_inbox()
        self.backend = "personal_gmail"
        self.email = email
        return email
    
    def get_verification_code(self) -> Optional[str]:
        """Aguarda e retorna código de verificação."""
        if not self.personal_service:
            logger.error("Nenhum serviço ativo")
            return None
        
        return self.personal_service.get_verification_code()
    
    def cleanup(self):
        """Limpa recursos."""
        if self.personal_service:
            self.personal_service.cleanup()
