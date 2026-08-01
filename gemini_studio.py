import os
import json
import requests
import base64
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from database import SessionLocal, ScrapedKnowledge

TEXT_MODEL = "models/gemini-flash-latest"
IMAGE_MODEL = "models/gemini-flash-latest"

ORG_CONTEXT = """
Empresa: VisionAI — Enxergando o Futuro com Inteligência
LinkedIn: linkedin.com/company/visionaicombr
Slogan: "Enxergando o Futuro com Inteligência"
Website: https://visionai.com.br

Linhas de Serviço (extraídas do site real):
1. IA Multimodal & Atendimento — Atendimento automático que analisa áudio, vídeo e imagem juntos em segundos. Assistente de voz com memória de contexto. URA com compreensão contextual.
2. Visão Computacional & Edge — Análise automática de câmeras existentes processando localmente sem nuvem. Fiscalização automática de EPIs. Rastreamento de ativos e logística. Mapas de calor de ocupação.
3. Realidade Mista & EdTech — Treinamentos em Realidade Mista (Meta Quest 3). Simulação de cenários perigosos. Treinamento de empatia para neurodiversidade. Acessibilidade visual e sonora.
4. Visão Agro-Industrial — Monitoramento de lavouras com câmeras e drones. Detecção de pragas antes da perda da safra. Manutenção preditiva industrial. Processamento local sem internet.
5. Geração de Conteúdo & Analytics — Produção automatizada de vídeos e apresentações (3 semanas → 2 dias). Análise de engajamento. Apresentações comerciais personalizadas por segmento.
6. Governança Corporativa & Intelligence — Sites corporativos, painéis de inteligência de mercado, rastreamento automático de concorrência.

Diferenciais técnicos:
- Processamento na borda (Edge AI) sem dependência de nuvem
- Integração com câmeras já instaladas pelo cliente
- IA que processa áudio, vídeo e documentos simultaneamente
- Resultados: +15% produtividade agro, 95% precisão em atendimento, ciclo de conteúdo de 3 semanas para 2 dias
- Ambiente VR multi-usuário com física realista

Tom de voz: Técnico, orientado a resultado real, sem hype, direto ao ponto
Idioma: Português do Brasil (profissional mas acessível)
Público-alvo: C-Levels, Heads de Operação, Diretores de TI, Gestores Industriais e do Agronegócio
"""

class GeminiStudio:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY") or ""
        self.client = genai.Client(api_key=api_key)
        self.model = TEXT_MODEL
        self.fallback_models = ["models/gemini-flash-latest", "models/gemini-pro-latest"]
        self.scraped_context = self._scrape_visionai_website()

    def _scrape_visionai_website(self) -> str:
        """Scrape limpo do site e bundles da SPA visionai.com.br para extrair conteúdo das 6 linhas de serviço."""
        import re
        from database import init_db
        init_db()
        db = SessionLocal()
        try:
            # Cache: se já foi feito scraping recente (< 24h), usa do banco
            knowledge = db.query(ScrapedKnowledge).filter_by(category="institucional_v2").first()
            if knowledge and knowledge.content and len(knowledge.content) > 100:
                return f"\n\nCONTEÚDO DO SITE VISIONAI.COM.BR:\n{knowledge.content}"
            
            home_resp = requests.get("https://visionai.com.br", timeout=4)
            js_urls = re.findall(r'/assets/[^"]+\.js', home_resp.text)
            
            extracted = []
            js_code_words = {'function', 'document', 'var ', 'const ', 'return', 'element', 'import',
                             'catch', 'math', 'void ', '==', '=>', 'childlist', 'undefined', 'props',
                             'classname', 'queryselectorall', 'addeventlistener', 'dataset', 'innerhtml'}
            
            for js_path in js_urls[:2]:
                try:
                    js_resp = requests.get(f"https://visionai.com.br{js_path}", timeout=4)
                    content = js_resp.text
                    strings = re.findall(r'"([^"\\]{25,300})"', content)
                    seen = set()
                    for t in strings:
                        t = t.strip()
                        t_lower = t.lower()
                        if t in seen or t.startswith('http') or len(t.split()) < 3:
                            continue
                        if any(w in t_lower for w in js_code_words):
                            continue
                        seen.add(t)
                        extracted.append(t)
                except Exception:
                    continue
            
            if extracted:
                text = "\n".join(extracted[:50])
                if knowledge:
                    knowledge.content = text
                else:
                    db.add(ScrapedKnowledge(category="institucional_v2", url="https://visionai.com.br", content=text))
                db.commit()
                return f"\n\nCONTEÚDO DO SITE VISIONAI.COM.BR:\n{text}"
        except Exception as e:
            print(f"Aviso no scraping do site visionai.com.br: {e}")
        finally:
            db.close()
        return ""

    def _generate(self, prompt: str, temperature: float = 0.8) -> str:
        for m in self.fallback_models:
            try:
                response = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=2048,
                    ),
                )
                self.model = m
                return response.text or ""
            except Exception as e:
                print(f"Modelo {m} falhou em _generate: {e}")
                continue
        return f"[Erro Gemini: Nenhum modelo disponível para a chave configurada]"

    def _generate_with_search(self, prompt: str, temperature: float = 0.8) -> str:
        """Gera conteúdo ativando Google Search Grounding para obter informações dinâmicas e atualizadas da internet."""
        for m in self.fallback_models:
            try:
                response = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=2048,
                        tools=[{"google_search": {}}]
                    ),
                )
                self.model = m
                return response.text or ""
            except Exception as e:
                print(f"Geração com busca no modelo {m} falhou: {e}. Tentando sem grounding...")
                try:
                    return self._generate(prompt, temperature=temperature)
                except Exception:
                    continue
        return self._generate(prompt, temperature=temperature)

    def _get_official_logo_b64(self) -> str:
        """Carrega e redimensiona a logomarca oficial do site visionai.com.br."""
        import os, io, base64
        from PIL import Image

        possible_paths = [
            os.path.join(os.path.dirname(__file__), "logo.png"),
            "/app/logo.png",
            "/home/hufema/vizionai/08_Governance_Corporate/Visionai_Corporate_Web/public/logo.png"
        ]

        for p in possible_paths:
            if os.path.exists(p):
                try:
                    img = Image.open(p)
                    img = img.resize((96, 96), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    return base64.b64encode(buf.getvalue()).decode("utf-8")
                except Exception as e:
                    print(f"Erro ao carregar logo de {p}: {e}")
                    continue
        return ""

    def _generate_svg_banner(self, title: str, category: str = "VisionAi Insights") -> str:
        """Gera um banner SVG corporativo 1200x630 com a logomarca e paleta oficial do site visionai.com.br (#9EFF00)."""
        import base64
        logo_b64 = self._get_official_logo_b64()
        logo_tag = f'<image href="data:image/png;base64,{logo_b64}" x="125" y="115" width="44" height="44"/>' if logo_b64 else '<rect x="125" y="115" width="44" height="44" rx="10" fill="url(#vision-grad)"/>'

        first_line = title.strip().split("\n")[0]
        clean_first_line = first_line.replace("#", "").replace("**", "").strip()
        clean_title = (clean_first_line[:75] + "...") if len(clean_first_line) > 75 else clean_first_line
        clean_category = category.upper()
        
        svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#050505"/>
      <stop offset="50%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#111111"/>
    </linearGradient>
    <linearGradient id="vision-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#9EFF00"/>
      <stop offset="100%" stop-color="#0055FF"/>
    </linearGradient>
    <linearGradient id="card-bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="rgba(255,255,255,0.06)"/>
      <stop offset="100%" stop-color="rgba(255,255,255,0.02)"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="30" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <!-- Background corporativo oficial (#050505) -->
  <rect width="1200" height="630" fill="url(#bg)"/>
  
  <!-- Glows com tom verde oficial (#9EFF00) -->
  <circle cx="150" cy="120" r="180" fill="#9EFF00" opacity="0.12" filter="url(#glow)"/>
  <circle cx="1050" cy="500" r="220" fill="#0055FF" opacity="0.15" filter="url(#glow)"/>
  
  <!-- Linhas Guia da Computação Visual -->
  <path d="M 0 150 L 1200 150 M 0 300 L 1200 300 M 0 450 L 1200 450" stroke="rgba(158, 255, 0, 0.05)" stroke-width="1"/>
  <path d="M 300 0 L 300 630 M 600 0 L 600 630 M 900 0 L 900 630" stroke="rgba(158, 255, 0, 0.05)" stroke-width="1"/>

  <!-- Telemetria HUD retículo em Verde Neon (#9EFF00) -->
  <g opacity="0.7">
    <path d="M 980 160 L 1020 160 M 980 160 L 980 200" stroke="#9EFF00" stroke-width="2" fill="none"/>
    <path d="M 1120 160 L 1080 160 M 1120 160 L 1120 200" stroke="#9EFF00" stroke-width="2" fill="none"/>
    <rect x="980" y="140" width="140" height="18" fill="rgba(158, 255, 0, 0.2)" rx="2"/>
    <text x="985" y="153" font-family="'Inter', monospace" font-size="10" fill="#9EFF00" font-weight="700">AI DETECT: 99.8%</text>
  </g>

  <!-- Container de Vidro Glassmorphism -->
  <rect x="80" y="80" width="1040" height="470" rx="24" fill="url(#card-bg)" stroke="rgba(158,255,0,0.2)" stroke-width="1.5"/>
  
  <!-- Logo Oficial & Nome da Marca (VISION + AI em #9EFF00) -->
  <g transform="translate(130, 130)">
    {logo_tag}
    <text x="58" y="32" font-family="'Outfit', 'Inter', sans-serif" font-weight="900" font-size="26" fill="#ffffff" letter-spacing="-0.5">VISION<tspan fill="#9EFF00">AI</tspan></text>
    <text x="210" y="32" font-family="'Inter', sans-serif" font-weight="400" font-size="14" fill="#94a3b8">| Corporate Tech</text>
  </g>
  
  <!-- Selo de Categoria com Cores do Site -->
  <g transform="translate(900, 135)">
    <rect width="180" height="34" rx="17" fill="rgba(158, 255, 0, 0.12)" stroke="rgba(158, 255, 0, 0.45)" stroke-width="1.5"/>
    <text x="90" y="22" font-family="'Inter', sans-serif" font-weight="800" font-size="11" fill="#9EFF00" text-anchor="middle" letter-spacing="1">{clean_category}</text>
  </g>

  <!-- Título Principal em PT-BR -->
  <foreignObject x="130" y="210" width="940" height="220">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: 'Outfit', 'Inter', system-ui, sans-serif; color: #f8fafc; font-size: 40px; font-weight: 700; line-height: 1.25; letter-spacing: -1px; text-shadow: 0 4px 12px rgba(0,0,0,0.5);">
      {clean_title}
    </div>
  </foreignObject>

  <!-- Linha de Acento Verde-Azul -->
  <rect x="130" y="460" width="140" height="4" rx="2" fill="url(#vision-grad)"/>

  <!-- Rodapé Institucional do Site -->
  <text x="130" y="500" font-family="'Inter', sans-serif" font-weight="500" font-size="16" fill="#94a3b8">Inovação, Inteligência Artificial &amp; Computação na Borda</text>
  <text x="1070" y="500" font-family="'Inter', sans-serif" font-weight="800" font-size="15" fill="#9EFF00" text-anchor="end">visionai.com.br ✦</text>
</svg>"""
        return base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')

    def get_auto_topics(self, category: str = None, force_refresh: bool = False) -> list:
        """Gera ou filtra tópicos B2B cobrindo as 6 linhas de serviço reais do site visionai.com.br."""
        import re as _re

        fallback_topics = [
            {"topic": "As câmeras que você já tem instaladas podem fiscalizar EPIs 24h/dia — sem nenhum humano olhando. Isso já é realidade com Edge AI", "category": "Visão Computacional", "format": "insight", "tone": "direto"},
            {"topic": "Fluxo invisível no armazém? Rastreamos 100% dos ativos, veículos e pessoas em tempo real — sem nova infraestrutura, só IA nas câmeras existentes", "category": "Visão Computacional", "format": "case", "tone": "tecnico"},
            {"topic": "Seu cliente envia foto + áudio + documento. Nossa IA analisa tudo em segundos com 95% de precisão. Isso é atendimento multimodal real", "category": "IA Multimodal", "format": "educativo", "tone": "tecnico"},
            {"topic": "URA que perde o fio quando o usuário muda de assunto? Criamos assistentes de voz com memória de contexto que executam ações em tempo real", "category": "IA Multimodal", "format": "provocativo", "tone": "provocativo"},
            {"topic": "No Meta Quest 3, simulamos cenários de risco real onde o erro não tem consequência — retenção 4x mais eficaz que treinamento convencional", "category": "EdTech & VR", "format": "case", "tone": "inspirador"},
            {"topic": "Como medir engajamento real em salas de aula e treinamentos corporativos com visão computacional ética e análise temporal em tempo real", "category": "EdTech & VR", "format": "storytelling", "tone": "visionario"},
            {"topic": "Perdas de safra por identificação tardia de pragas. Detectamos anomalias agrícolas dias antes de serem visíveis a olho nu — +15% produtividade, menos defensivos", "category": "Agro-Industrial", "format": "case", "tone": "inspirador"},
            {"topic": "Máquinas parando sem aviso em produção? Identificamos desgaste no hardware local, sem depender de nuvem. Manutenção preditiva onde não chega internet", "category": "Agro-Industrial", "format": "insight", "tone": "direto"},
            {"topic": "Produção de vídeo institucional: 3 semanas de trabalho → 2 dias com automação IA (roteiro, narração e edição automatizados)", "category": "Conteúdo & Mídia IA", "format": "storytelling", "tone": "visionario"},
            {"topic": "Propostas comerciais genéricas não fecham negócio. Geramos apresentações personalizadas por segmento de cliente de forma automática", "category": "Conteúdo & Mídia IA", "format": "lista", "tone": "direto"},
            {"topic": "Sua equipe gasta horas coletando dados de concorrentes manualmente? Automatizamos a inteligência competitiva com relatórios executivos em minutos", "category": "Governança & Intelligence", "format": "lista", "tone": "provocativo"},
            {"topic": "Portais corporativos orientados a conversão B2B: construímos ecossistemas digitais de alta credibilidade para decisores C-Level", "category": "Governança & Intelligence", "format": "insight", "tone": "educativo"},
        ]

        topics_list = []
        if force_refresh:
            site_content = self.scraped_context or ""
            cat_prompt = f" com foco exclusivo na categoria '{category}'" if category else ""
            prompt = f"""
Você é um estrategista de conteúdo LinkedIn B2B para a empresa VisionAI (https://visionai.com.br).

INFORMAÇÕES DA EMPRESA:
{ORG_CONTEXT}

CONTEÚDO REAL DO SITE:
{site_content[:2000]}

Gere EXATAMENTE 12 ideias de posts B2B{cat_prompt}, distribuídos entre as 6 linhas de serviço da VisionAI:
1. Visão Computacional (Câmeras existentes, EPIs, Rastreamento, Edge AI)
2. IA Multimodal (OmniVoice, Voz+Vídeo+Texto, URA Cognitiva)
3. EdTech & VR (Realidade Mista, Meta Quest 3, Engajamento Educacional)
4. Agro-Industrial (Drones, Manutenção Preditiva Offline, Detecção Pragas)
5. Conteúdo & Mídia IA (Vídeos Corporativos, Apresentações Automatizadas)
6. Governança & Intelligence (Portais Executivos, Análise Competitiva)

REGRAS:
- NUNCA mencionar SAP
- Responda APENAS JSON válido sem markdown:
[{"topic": "...", "category": "Visão Computacional|IA Multimodal|EdTech & VR|Agro-Industrial|Conteúdo & Mídia IA|Governança & Intelligence", "format": "insight|case|storytelling|lista", "tone": "direto|tecnico|provocativo|visionario"}]
"""
            try:
                raw = self._generate(prompt, temperature=0.85)
                json_match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, list) and len(parsed) > 0:
                        topics_list = parsed
            except Exception as e:
                print(f"Aviso ao gerar tópicos via Gemini: {e}")

        if not topics_list:
            topics_list = fallback_topics

        if category:
            cat_lower = category.lower()
            filtered = [t for t in topics_list if cat_lower in t.get("category", "").lower()]
            return filtered if filtered else topics_list

        return topics_list

    def _composite_advertising_creative(self, raw_img_bytes: bytes, pt_headline: str, category: str = "VisionAi Insights") -> tuple[str, str]:
        """
        Combina a foto realista gerada por IA com a Moldura Publicitária oficial da VisionAI
        usando a logomarca do site (logo.png) e paleta de cores corporativa (#9EFF00 / #0055FF).
        """
        import io, html
        from PIL import Image
        import cairosvg

        try:
            # 1. Carrega e redimensiona a foto de fundo para 1200x630
            bg = Image.open(io.BytesIO(raw_img_bytes)).convert("RGB")
            bg = bg.resize((1200, 630), Image.Resampling.LANCZOS)

            # 2. Carrega a logo oficial
            logo_b64 = self._get_official_logo_b64()
            logo_tag = f'<image href="data:image/png;base64,{logo_b64}" x="80" y="55" width="44" height="44"/>' if logo_b64 else '<rect x="80" y="55" width="44" height="44" rx="10" fill="url(#vision-grad)"/>'

            # 3. Formata manchete em PT-BR para o SVG overlay usando tspan nativo
            def wrap_text_to_tspans(text: str, max_chars: int = 42, start_x: int = 80, dy: int = 48) -> str:
                words = text.strip().replace('#', '').replace('*', '').split()
                lines = []
                current_line = []
                current_len = 0
                for word in words:
                    if current_len + len(word) + 1 > max_chars and current_line:
                        lines.append(" ".join(current_line))
                        current_line = [word]
                        current_len = len(word)
                    else:
                        current_line.append(word)
                        current_len += len(word) + 1
                if current_line:
                    lines.append(" ".join(current_line))
                
                lines = lines[:4]
                tspans = []
                for i, l in enumerate(lines):
                    d = 0 if i == 0 else dy
                    escaped_line = html.escape(l)
                    tspans.append(f'<tspan x="{start_x}" dy="{d}">{escaped_line}</tspan>')
                return "\n".join(tspans)

            first_line = pt_headline.strip().split("\n")[0]
            clean_first_line = first_line.replace("#", "").replace("**", "").strip()
            headline_tspans = wrap_text_to_tspans(clean_first_line)
            clean_category = html.escape(category.upper())

            # 4. Moldura gráfica oficial com a paleta do site (#9EFF00)
            svg_overlay = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="vision-grad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#9EFF00"/>
      <stop offset="100%" stop-color="#0055FF"/>
    </linearGradient>
    <linearGradient id="shadow" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="rgba(5,5,5,0.92)"/>
      <stop offset="60%" stop-color="rgba(5,5,5,0.55)"/>
      <stop offset="100%" stop-color="rgba(5,5,5,0.20)"/>
    </linearGradient>
  </defs>

  <!-- Gradiente de escurecimento escuro (#050505) -->
  <rect width="1200" height="630" fill="url(#shadow)"/>

  <!-- Telemetria HUD Visão Computacional em Verde Neon (#9EFF00) -->
  <g opacity="0.7">
    <path d="M 950 140 L 980 140 M 950 140 L 950 170" stroke="#9EFF00" stroke-width="2" fill="none"/>
    <path d="M 1080 140 L 1050 140 M 1080 140 L 1080 170" stroke="#9EFF00" stroke-width="2" fill="none"/>
    <path d="M 950 240 L 980 240 M 950 240 L 950 210" stroke="#9EFF00" stroke-width="2" fill="none"/>
    <path d="M 1080 240 L 1050 240 M 1080 240 L 1080 210" stroke="#9EFF00" stroke-width="2" fill="none"/>
    <rect x="950" y="122" width="130" height="16" fill="rgba(158, 255, 0, 0.2)" rx="2"/>
    <text x="955" y="134" font-family="'Inter', monospace" font-size="10" fill="#9EFF00" font-weight="bold">AI DETECT: 99.8%</text>
  </g>

  <!-- Cabeçalho: Logo Oficial PNG + Marca VISION AI (#9EFF00) -->
  <g transform="translate(80, 55)">
    {logo_tag}
    <text x="54" y="32" font-family="'Outfit', 'Inter', sans-serif" font-weight="900" font-size="26" fill="#ffffff" letter-spacing="-0.5">VISION<tspan fill="#9EFF00">AI</tspan></text>
    <text x="205" y="32" font-family="'Inter', sans-serif" font-weight="400" font-size="14" fill="#94a3b8">| Corporate Tech</text>
  </g>

  <!-- Selo de Categoria Oficial em Verde Neon (#9EFF00) -->
  <g transform="translate(920, 58)">
    <rect width="200" height="36" rx="18" fill="rgba(158, 255, 0, 0.12)" stroke="rgba(158, 255, 0, 0.45)" stroke-width="1.5"/>
    <text x="100" y="23" font-family="'Inter', sans-serif" font-weight="800" font-size="12" fill="#9EFF00" text-anchor="middle" letter-spacing="1">{clean_category}</text>
  </g>

  <!-- Título Principal do Criativo em PT-BR -->
  <text x="80" y="220" font-family="'Outfit', 'Inter', sans-serif" font-size="38" fill="#ffffff" font-weight="800">
    {headline_tspans}
  </text>

  <!-- Rodapé Publicitário Oficial (#9EFF00 / #0055FF) -->
  <rect x="80" y="535" width="140" height="4" rx="2" fill="url(#vision-grad)"/>
  <text x="80" y="575" font-family="'Inter', sans-serif" font-weight="500" font-size="14" fill="#94a3b8">Inovação, Inteligência Artificial &amp; Computação na Borda</text>
  <text x="1120" y="575" font-family="'Inter', sans-serif" font-weight="800" font-size="15" fill="#9EFF00" text-anchor="end">visionai.com.br ✦</text>
</svg>"""

            # 5. Renderiza moldura e faz composição alfa sobre a foto
            overlay_png = cairosvg.svg2png(bytestring=svg_overlay.encode('utf-8'))
            overlay_img = Image.open(io.BytesIO(overlay_png)).convert('RGBA')

            composite = Image.alpha_composite(bg.convert('RGBA'), overlay_img)
            out = io.BytesIO()
            composite.convert('RGB').save(out, format='JPEG', quality=95)
            
            img_b64 = base64.b64encode(out.getvalue()).decode('utf-8')
            print("Peça publicitária corporativa oficial (foto + branding do site VisionAI) criada com sucesso!")
            return img_b64, "image/jpeg"
        except Exception as e:
            print(f"Erro ao compor peça publicitária: {e} — usando foto original")
            img_b64 = base64.b64encode(raw_img_bytes).decode('utf-8')
            return img_b64, "image/jpeg"

    def _generate_image_base64(self, prompt: str, pt_title: str = "VisionAI Insights", category: str = "VisionAi Insights") -> tuple[str, str]:
        """Gera uma imagem realista pura e compõe a peça publicitária com branding VisionAI. Retorna (base64, mime_type)."""
        clean_prompt = prompt.replace("\n", " ").strip()
        negative_rules = ", NO sci-fi, NO futuristic fantasy, NO glowing cyber portals, NO text, NO written words, NO letters, NO signs, NO typography, authentic realistic professional corporate photography, 35mm lens, Sony Alpha camera, natural lighting, highly realistic 8k photo"
        full_prompt = clean_prompt + negative_rules if "NO text" not in clean_prompt else clean_prompt

        # Tenta modelos ativos de imagem (Gemini 3.1 Flash Image & Imagen 4)
        for model in ["gemini-3.1-flash-image", "imagen-4.0-fast-generate-001", "gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"]:
            try:
                if "imagen" in model:
                    res = self.client.models.generate_images(
                        model=model,
                        prompt=full_prompt,
                        config=types.GenerateImagesConfig(number_of_images=1, output_mime_type="image/jpeg")
                    )
                    if res.generated_images:
                        img_bytes = res.generated_images[0].image.image_bytes
                        return self._composite_advertising_creative(img_bytes, pt_headline=pt_title, category=category)
                else:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["TEXT", "IMAGE"],
                            temperature=0.6,
                        )
                    )
                    for part in response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.data:
                            img_bytes = part.inline_data.data
                            return self._composite_advertising_creative(img_bytes, pt_headline=pt_title, category=category)
            except Exception as e:
                print(f"Modelo de imagem {model} falhou: {e}")
                continue

        # Fallback: SVG corporativo VisionAI com título em Português (PT-BR)
        print("Usando banner SVG corporativo como fallback visual com título em Português.")
        svg_b64 = self._generate_svg_banner(title=pt_title)
        return svg_b64, "image/svg+xml"

    def _clean_post_content(self, text: str) -> tuple[str, str]:
        """
        Remove cercas markdown (```markdown), preâmbulos conversacionais da IA, rótulos de títulos (ex: '1. TITLE:')
        e limpa asteriscos markdown (**bold**, *italic*, # Header) incompatíveis com a publicação nativa do LinkedIn.
        Retorna (texto_limpo_completo, titulo_manchete_limpo).
        """
        import re
        if not text:
            return ("", "VisionAI Insights")
        
        # 1. Remove cercas de código ```markdown
        cleaned = re.sub(r"^```(?:markdown|text|json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())

        # 2. Limpeza rigorosa de marcações Markdown incompatíveis com LinkedIn (asteriscos **, *, hashes #)
        # Converte negritos markdown **texto** -> texto (remove os asteriscos brutos)
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        # Converte itálicos ou asteriscos avulsos *texto* -> texto
        cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
        # Converte títulos markdown (# Título -> Título)
        cleaned = re.sub(r"^[#]+\s*(.+)$", r"\1", cleaned, flags=re.MULTILINE)
        # Substitui tópicos marcados com asterisco/trífen no início da linha por emojis elegantes
        cleaned = re.sub(r"^\*\s+", "▸ ", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\-\s+", "▸ ", cleaned, flags=re.MULTILINE)

        lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
        
        # 3. Filtra preâmbulos conversacionais, sugestões de banner entre colchetes ou prefixos de prompt nas primeiras linhas
        meta_patterns = [
            r"^aqui está", r"^segue ", r"^com base ", r"^conforme ", r"^proposta de post",
            r"^olá", r"^prezado", r"^\d+\.\s*title:", r"^title:", r"^título:", r"^post:", r"^assunto:", r"^prompt:",
            r"^\[sugestão", r"^\[imagem", r"^\[banner", r"^\[foto", r"^\[note", r"^\[nota"
        ]
        
        while lines:
            first_line = lines[0].lower()
            is_meta = False
            if lines[0].startswith("[") and lines[0].endswith("]"):
                is_meta = True
            else:
                for pat in meta_patterns:
                    if re.search(pat, first_line):
                        is_meta = True
                        break
            if is_meta:
                lines.pop(0)
            else:
                break
                
        clean_full_text = "\n\n".join(lines)
        
        # 4. Encontra a melhor manchete em português para a faixa do criativo
        clean_headline = "VisionAI Insights"
        for line in lines:
            clean_l = re.sub(r"^[\#\*\d\.\-\s]+", "", line).strip()
            clean_l = re.sub(r"^(?:hook|desafio|solução|insight|paradigm shift|pilar \d+):\s*", "", clean_l, flags=re.IGNORECASE).strip()
            if len(clean_l) >= 12 and not clean_l.endswith(":"):
                clean_headline = clean_l
                break
                
        return (clean_full_text, clean_headline)

    def regenerate_media_from_revised_text(self, revised_text: str, media_type: str = "image") -> dict:
        """
        Recebe o texto editado pelo usuário e gera uma nova peça visual (imagem ou banner)
        que representa fielmente a versão final revisada pelo usuário, com manchete estilo Clickbait B2B.
        """
        clean_full_text, fallback_headline = self._clean_post_content(revised_text)

        prompt = f"""
Você é o Diretor de Criação & Diretor de Fotografia Corporativa Sênior da VisionAI (visionai.com.br).

TEXTO DO POST NO LINKEDIN:
---
{clean_full_text[:2000]}
---

SUAS TAREFAS:
1. **SELO DE CATEGORIA**: Identifique a linha de serviço em Português (Ex: VISÃO AGRO-INDUSTRIAL, REALIDADE MISTA & VR, IA MULTIMODAL & SAC, VISÃO COMPUTACIONAL, GOVERNANÇA CORPORATIVA).
2. **MANCHETE CLICKBAIT B2B**: Crie uma manchete provocativa, magnética e de alta conversão em PORTUGUÊS (estilo Clickbait B2B Executivo, de 6 a 12 palavras) para estamparmos no Banner do Criativo Visual.
   - NUNCA copie simplesmente a primeira frase do texto do post.
   - A manchete deve gerar curiosidade extrema no leitor C-Level (CEOs, CTOs, VPs de Operações).
   Exemplos de Manchetes Clickbait B2B:
   - "O Erro Estratégico na Nuvem Que Custa Milhões às Indústrias"
   - "Por Que o Treinamento Tradicional Falha em 90% dos Casos?"
   - "A Verdade Sobre o Monitoramento de Safra Que Ninguém Te Conta"
   - "O Erro Que Custava Vidas Agora Custa Zero Para Sua Operação"
3. **PROMPT DE FOTOGRAFIA EM INGLÊS**: Crie um prompt de imagem em INGLÊS que descreva UMA FOTOGRAFIA CORPORATIVA REALISTA 100% ADERENTE E FIEL ao tema do texto.

REGRAS RÍGIDAS DE ADERÊNCIA AO TEXTO E FOTOGRAFIA REALISTA:
- EXTREMA ADERÊNCIA AO TEMA DO TEXTO:
  * Se o texto for sobre AGRO/LAVOURA: foto de campo agrícola real de milho/soja com agrônomo e drone de monitoramento.
  * Se o texto for sobre VR/META QUEST 3: foto de profissional em escritório usando headset VR Meta Quest 3 em treinamento de segurança.
  * Se o texto for sobre ATENDIMENTO/SAC MULTIMODAL: foto de especialista de atendimento com headset em mesa corporativa moderna com monitores de dados.
  * Se o texto for sobre FÁBRICA/EPIs: foto de galpão industrial com câmera dome CCTV no teto e operadores com capacetes/coletes.
  * Se o texto for sobre GOVERNANÇA/C-LEVEL: foto de executivos em sala de reunião corporativa analisando painéis operacionais.
- NUNCA USE CÂMERAS DE FÁBRICA SE O TEXTO FOR SOBRE AGRO, VR OU ATENDIMENTO!
- PROIBIDO SCI-FI: NUNCA crie portais virtuais, raios laser ou néons brilhantes irreais. A imagem deve parecer uma fotografia real de reportagem da Forbes/Harvard Business Review.
- SEM TEXTO EM PIXELS: NUNCA coloque palavras ou letras no prompt da imagem.
- ADICIONE NO FINAL DO PROMPT: 'authentic realistic professional corporate photography, Hasselblad medium format camera, natural office or factory lighting, sharp focus, 8k resolution, NO sci-fi, NO text, NO letters, NO typography'.

Responda APENAS com JSON:
{{
  "category": "NOME_CURTO_DA_CATEGORIA_EM_PT",
  "clickbait_headline": "Manchete Provocativa Clickbait B2B em Português",
  "image_prompt": "prompt de fotografia aderente ao texto em inglês"
}}
"""
        raw = self._generate(prompt, temperature=0.75)
        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        image_prompt = ""
        category_name = "VISIONAI INSIGHTS"
        clickbait_headline = ""
        if json_match:
            try:
                data = json.loads(json_match.group())
                image_prompt = data.get("image_prompt", "")
                category_name = data.get("category", "VISIONAI INSIGHTS")
                clickbait_headline = data.get("clickbait_headline", "").strip()
            except Exception:
                pass
        
        if not image_prompt:
            image_prompt = f"Corporate tech photo representing: {clean_full_text[:100]}"
            
        final_banner_title = clickbait_headline if (clickbait_headline and len(clickbait_headline) >= 10) else fallback_headline
        img_b64, mime = self._generate_image_base64(image_prompt, pt_title=final_banner_title, category=category_name)
        return {
            "category": category_name,
            "creative_headline": final_banner_title,
            "image_prompt": image_prompt,
            "image_base64": img_b64,
            "image_mime": mime,
            "media_type": media_type
        }

    # ── 1. GERAÇÃO DE POSTS ────────────────────────────────────────────────────
    def generate_post(self, topic: str, format_type: str = "standard", tone: str = "visionario", media_type: str = "image", voice_mode: str = "corporate") -> dict:
        """Gera um post completo usando um fluxo estritamente sequencial em 2 etapas:
           ETAPA 1: Criação do texto final do post (modo corporativo ou founder/1ª pessoa).
           ETAPA 2: Análise do texto final gerado para criar a arte visual com 100% de alinhamento semântico.
        """
        format_guides = {
            "pulse_article": (
                "Artigo Estratégico LinkedIn Pulse / Essay (350-500 palavras) — Estrutura de Liderança de Pensamento de Alto Nível C-Suite "
                "(inspirado no estudo 'Computer Vision: Becoming the Next Strategic Sensor'):\n"
                "1. TITLE: Título executivo provocativo\n"
                "2. HOOK: Reenquadre a visão tradicional da tecnologia.\n"
                "3. PARADIGM SHIFT: A transição para a inteligência operacional na borda (Edge AI).\n"
                "4. 3 PILARES ESTRATÉGICOS da VisionAI.\n"
                "5. ROI E IMPACTO OPERACIONAL (métricas reais).\n"
                "6. EXECUTIVE ROADMAP & CALL TO ACTION."
            ),
            "strategic_framework": (
                "Framework Executivo & Manifesto (250-400 palavras) — Modelo conceitual proprietário da VisionAI para transformar a operação. "
                "Passos claros de arquitetura Edge AI e Visão Computacional."
            ),
            "case": (
                "Estudo de Caso Executivo (200-350 palavras) — Focado estritamente em ROI e Operações Reais da VisionAI. "
                "Desafio, Solução Aplicada e Métricas de Impacto."
            ),
            "storytelling": (
                "Storytelling Corporativo (200-300 palavras) — Narrativa envolvente sobre transformação de operações com IA da VisionAI."
            ),
            "insight": (
                "Insight Provocativo C-Level (150-250 palavras) — Provocação executiva desafiando dogmas do mercado."
            ),
            "standard": (
                "Post B2B Padrão + Banner (150-250 palavras) — Post executivo direto ao ponto com gancho poderoso e CTA."
            )
        }

        tone_guides = {
            "visionario": "Tom visionário e autoritativo — questione o status quo com pragmatismo executivo, provoque reflexão profunda no C-level",
            "tecnico": "Tom analítico e arquitetural — cite processamento na borda (Edge AI), latência, segurança sem nuvem e ROI mensurável",
            "inspirador": "Tom focado em transformação de negócios e impacto real na sociedade e nas operações humanas",
            "educativo": "Tom consultivo de alta liderança, educando o mercado sobre os benefícios reais da inteligência artificial aplicada",
        }

        voice_instruction = (
            "PERFIL DE VOZ INSTITUCIONAL (VisionAI Company Page): Escreva com autoridade corporativa institucional."
            if voice_mode == "corporate" else
            "PERFIL DE VOZ FOUNDER / THOUGHT LEADERSHIP (Perfil Pessoal de Executivo): Escreva em 1ª PESSOA ('Eu', 'Nossa equipe', 'Conversando com um CTO essa semana...'). Conte uma história profissional real e termine com uma provocação executiva."
        )

        # ── ETAPA 1: GERAÇÃO DO TEXTO DO POST ──────────────────────────────────
        text_prompt = f"""
Você é um Copywriter Executivo B2B Sênior e Diretor de Growth Marketing da VisionAI (visionai.com.br).

CONTEXTO INSTITUCIONAL E TÉCNICO DA VISIONAI:
{ORG_CONTEXT}
{self.scraped_context}

SUA MISSÃO: Escrever um post publicitário, humano e de altíssimo engajamento executivo para o LinkedIn Corporativo sobre o tema abaixo.

PERFIL DE NARRATIVA: {voice_instruction}
TEMA/OBJETIVO: {topic}
FORMATO DE CONTEÚDO: {format_guides.get(format_type, format_guides['standard'])}
TOM DE VOZ: {tone_guides.get(tone, tone_guides['visionario'])}

DIRETRIZES DE COPYWRITING & FORMATAÇÃO (ESTRITAMENTE OBRIGATÓRIAS):
1. **ZERO ASTERISCOS OU MARKDOWN**:
   - PROIBIDO usar asteriscos (`**` ou `*`) para tentar colocar texto em negrito ou itálico. O LinkedIn NÃO aceita markdown e exibe os asteriscos brutos no feed.
   - PROIBIDO usar cerquilhas (`#`, `##`, `###`) como títulos.
   - Use emojis elegantes (como `✦`, `▸`, `⚡`, `💡`, `👉`, `📍`) no início de tópicos para destacar pontos cruciais de forma limpa.

2. **COPYWRITING HUMANO E PUBLICITÁRIO (NADA ROBÓTICO OU ARTIFICIAL)**:
   - PROIBIDO clichês robóticos de IA como: "No mundo de hoje", "Em constante evolução", "Na era da Inteligência Artificial", "Em um cenário dinâmico", "Em suma", "Desbloquear o potencial", "Revolucionar a forma", "Vamos juntos".
   - Escreva com ritmo publicitário dinâmico, frases marcantes e autoridade corporativa real de quem lidera engenharia de IA e operações.
   - **HOOK PODEROSO**: As primeiras 2 linhas DEVEM parar o scroll no feed do LinkedIn com uma afirmação provocativa, dado chocante ou provocação estratégica.
   - Parágrafos curtos de no máximo 2 a 3 linhas para máxima legibilidade no celular.

3. **MÉTRICAS E DORES OPERACIONAIS REAIS**:
   - Cite números concretos e resultados reais (+15% produtividade no agro, 95% precisão em SAC, retenção 4x em VR, ciclo de vídeo de 3 semanas para 2 dias).
   - Aborde problemas reais: latência de streaming RTSP, estouro de orçamento de nuvem, fiscalização 24/7 de EPIs sem humanos na sala de controle, passivo trabalhista NR-12.

4. **FINALIZAÇÃO**:
   - Termine com uma Call to Action (CTA) executiva provocativa e 4 a 6 hashtags corporativas estratégicas (ex: #VisaoComputacional #EdgeAI #InteligenciaArtificial #VisionAI).

FORMATO DE SAÍDA: Retorne APENAS o texto do post em português, pronto para ser publicado. Sem explicações adicionais e SEM NENHUM ASTERISCO.
"""
        raw_post_text = self._generate(text_prompt, temperature=0.85).strip()
        post_text, _ = self._clean_post_content(raw_post_text)

        # ── ETAPA 2: GERAÇÃO DA ARTE VISUAL BASEADA NO TEXTO CRIADO ──────────────
        # O prompt visual e a imagem são criados APÓS o texto existir, com 100% de alinhamento com o seu significado!
        art_result = self.regenerate_media_from_revised_text(post_text, media_type=media_type)
        
        image_prompt = art_result.get("image_prompt", "")
        image_b64 = art_result.get("image_base64", "")
        image_mime = art_result.get("image_mime", "image/svg+xml")

        return {
            "topic": topic,
            "format": format_type,
            "tone": tone,
            "content": post_text,
            "category": art_result.get("category"),
            "creative_headline": art_result.get("creative_headline"),
            "image_prompt": image_prompt,
            "image_base64": image_b64,
            "image_mime": image_mime,
            "media_type": media_type,
            "char_count": len(post_text),
            "model": self.model,
            "image_model": IMAGE_MODEL if image_b64 else None
        }

    # ── 2. REVISÃO E MELHORIA DE POST ─────────────────────────────────────────
    def review_post(self, draft: str) -> dict:
        """Analisa e melhora um rascunho de post."""
        prompt = f"""
Você é um especialista em LinkedIn Marketing da VisionAi.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}

RASCUNHO DO POST:
{draft}

TAREFA: Analise este post e forneça:
1. PONTUAÇÃO (0-10) com justificativa breve
2. PONTOS FORTES (lista de 2-3 itens)
3. MELHORIAS SUGERIDAS (lista de 2-3 itens)
4. VERSÃO MELHORADA (reescreva o post aplicando as melhorias)

Responda em JSON com as chaves: "score", "strengths", "improvements", "improved_version"
"""
        raw = self._generate(prompt, temperature=0.5)
        try:
            # Tenta extrair JSON do texto
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"raw": raw, "model": self.model}

    # ── 3. ANÁLISE DE ANALYTICS ───────────────────────────────────────────────
    def analyze_analytics(self, analytics_data: dict) -> str:
        """Interpreta dados de analytics e gera insights executivos."""
        prompt = f"""
Você é analista sênior de marketing da VisionAi.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}

DADOS DE ANALYTICS DO LINKEDIN (últimos 12 meses):
{json.dumps(analytics_data, ensure_ascii=False, indent=2)}

TAREFA: Gere um relatório executivo em Português com:
1. **Resumo Executivo** (2-3 frases sobre a performance geral)
2. **Métricas-Chave** (destaque os números mais importantes)
3. **Tendências Identificadas** (o que está crescendo, o que está caindo)
4. **Diagnóstico** (por que esses resultados estão acontecendo)
5. **Recomendações Estratégicas** (3 ações concretas para melhorar)
6. **Próximos Passos** (o que fazer nas próximas 2 semanas)

Use markdown para formatação. Seja direto e orientado a dados.
"""
        return self._generate(prompt, temperature=0.4)

    # ── 4. ANÁLISE DE SEGUIDORES ──────────────────────────────────────────────
    def analyze_followers(self, follower_data: dict) -> str:
        """Gera insights sobre o perfil demográfico dos seguidores."""
        prompt = f"""
Você é estrategista de audiência da VisionAi.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}

DADOS DE SEGUIDORES:
{json.dumps(follower_data, ensure_ascii=False, indent=2)}

TAREFA: Analise o perfil dos seguidores e responda em Português:
1. **Quem está seguindo a VisionAi** (perfil dominante)
2. **Alinhamento com ICP** (Ideal Customer Profile — está alinhado com o público-alvo?)
3. **Oportunidades** (segmentos que podemos explorar mais)
4. **Gaps** (quem deveria seguir mas não está)
5. **Sugestões de conteúdo** baseadas no perfil da audiência

Use markdown. Seja específico e acionável.
"""
        return self._generate(prompt, temperature=0.5)

    # ── 5. ESTRATÉGIA DE CONTEÚDO ─────────────────────────────────────────────
    def generate_content_strategy(self, kpis: dict, period_days: int = 30) -> dict:
        """Gera um calendário editorial e estratégia de conteúdo."""
        prompt = f"""
Você é o Head de Marketing de Conteúdo da VisionAi.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}

KPIs ACTUAIS:
{json.dumps(kpis, ensure_ascii=False, indent=2)}

TAREFA: Crie uma estratégia de conteúdo para os próximos {period_days} dias.

Retorne um JSON com a seguinte estrutura:
{{
  "strategy_summary": "resumo da estratégia em 2-3 frases",
  "posting_frequency": "recomendação de frequência",
  "best_times": ["lista de melhores horários para postar"],
  "content_pillars": [
    {{"pillar": "nome do pilar", "percentage": 30, "rationale": "justificativa"}}
  ],
  "post_ideas": [
    {{"week": 1, "topic": "tema", "format": "formato", "hook": "gancho sugerido"}}
  ],
  "hashtag_strategy": ["hashtags recomendadas para a conta"],
  "kpi_targets": {{"followers_growth": "meta", "impressions": "meta", "engagement_rate": "meta"}}
}}

Gere ideias de posts para 4 semanas (2-3 posts por semana). Responda APENAS com o JSON.
"""
        raw = self._generate(prompt, temperature=0.7)
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"raw": raw, "model": self.model}

    # ── 6. INSIGHTS DO DASHBOARD ──────────────────────────────────────────────
    def generate_dashboard_insight(self, summary: dict) -> str:
        """Gera comentário executivo rápido para o dashboard."""
        prompt = f"""
Você é um CMO assistente da VisionAi. Em 2-3 frases directas e impactantes,
comente o estado actual do LinkedIn corporativo com base nestes dados:

{json.dumps(summary, ensure_ascii=False)}

Tom: executivo, directo, sem floreados. Use números. Indique 1 prioridade imediata.
Responda em Português do Brasil.
"""
        return self._generate(prompt, temperature=0.4)

    # ── 7. ANÁLISE DE POST INDIVIDUAL ─────────────────────────────────────────
    def analyze_single_post(self, post_content: str, post_metrics: dict = None) -> str:
        """Analisa performance e qualidade de um post específico."""
        metrics_section = ""
        if post_metrics:
            metrics_section = f"\nMÉTRICAS DO POST:\n{json.dumps(post_metrics, ensure_ascii=False)}\n"

        prompt = f"""
Analise este post do LinkedIn da VisionAi:

CONTEÚDO:
{post_content}
{metrics_section}
Forneça em Português:
- O que funcionou bem neste post
- O que poderia ser melhorado
- Como adaptar este conteúdo para gerar mais engajamento
- Sugestão de um post de seguimento (follow-up) sobre o mesmo tema

Use markdown. Seja específico e prático.
"""
        return self._generate(prompt, temperature=0.5)

    # ── 8. GERAÇÃO DE HASHTAGS ────────────────────────────────────────────────
    def generate_hashtags(self, topic: str, count: int = 8) -> list:
        """Gera hashtags optimizadas para um tópico específico."""
        prompt = f"""
Gere {count} hashtags do LinkedIn para um post da VisionAi sobre: "{topic}"

Contexto: {ORG_CONTEXT}

Misture hashtags em português e inglês. Inclua:
- 2-3 hashtags de alto volume (ex: #IA, #Tecnologia)
- 3-4 hashtags de nicho (mais específicas ao tema)
- 1-2 hashtags de marca ou sectorial

Retorne APENAS uma lista JSON de strings. Ex: ["#IA", "#TransformacaoDigital"]
"""
        raw = self._generate(prompt, temperature=0.6)
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return []

    # ── 9. RADAR DE TENDÊNCIAS DA WEB (DINÂMICO + PERSISTÊNCIA EM DB + EXCLUSÃO DE USADOS) ───────
    def fetch_web_trends(self, query: str = None, force_refresh: bool = False) -> dict:
        """Busca notícias e tendências em tempo real na web cobrindo os 6 pilares estratégicos da VisionAI.
           Salva no banco SQLite, ordena de forma aleatória a cada requisição e oculta automaticamente matérias usadas (used = True).
        """
        from database import init_db, SessionLocal, WebTrendItem
        from sqlalchemy.sql.expression import func
        import random, time, re, json

        init_db()
        db = SessionLocal()

        try:
            # 1. Se não for varredura forçada e houver pelo menos 6 itens não usados no banco, retorna uma amostragem ALEATÓRIA
            if not force_refresh:
                q = db.query(WebTrendItem).filter(WebTrendItem.used == False)
                if query:
                    q = q.filter(WebTrendItem.title.ilike(f"%{query}%") | WebTrendItem.summary.ilike(f"%{query}%") | WebTrendItem.category.ilike(f"%{query}%"))
                
                cached_items = q.order_by(func.random()).limit(12).all()
                if len(cached_items) >= 6:
                    return {
                        "trends": [
                            {
                                "id": item.id,
                                "title": item.title,
                                "category": item.category,
                                "summary": item.summary,
                                "impact_b2b": item.impact_b2b,
                                "suggested_topic": item.suggested_topic,
                                "used": item.used
                            }
                            for item in cached_items
                        ]
                    }

            # 2. Varredura dinâmica em tempo real na internet via Gemini + Google Search Grounding
            sectors = [
                "Visão Computacional e Inspeção de Qualidade em Fábricas com Edge AI",
                "Drones com Visão Preditiva e Sensores em Agrobusiness de Larga Escala",
                "Realidade Mista, Meta Quest 3 e Treinamento Imersivo em EdTech Corporativa",
                "SAC Multimodal com IA de Voz Humanizada e Atendimento ao Cliente",
                "Governança C-Level, Inteligência de Mercado e Radar de Concorrência",
                "Automação Generativa de Mídia, Marketing B2B e Geração de Conteúdo",
                "Robótica Industrial, Câmeras Inteligentes e Prevenção de Acidentes NR-12",
                "Processamento Local em Borda (Edge Computing) sem Dependência da Nuvem"
            ]
            
            chosen_sectors = random.sample(sectors, min(4, len(sectors)))
            if query:
                chosen_sectors.insert(0, query)
                
            search_query_str = " e ".join(chosen_sectors)
            timestamp_seed = int(time.time())

            prompt = f"""
Você é o Diretor de Inteligência de Mercado & Tendências Tecnológicas B2B da VisionAI (visionai.com.br).

SUA MISSÃO: Realize uma busca em tempo real na internet (Google Search) e traga exatamente de 8 a 12 tendências e notícias B2B RECENTES, REAIS E INÉDITAS sobre:
{search_query_str} (Seed de busca: {timestamp_seed}).

Traga notícias ricas e diversificadas cobrindo Agro, Indústria/NR-12, VR/Realidade Mista, Atendimento de Voz, Edge AI e Governança.

Responda APENAS com JSON no seguinte formato:
{{
  "trends": [
    {{
      "title": "Título impactante e específico da notícia/tendência real da internet",
      "category": "VISÃO AGRO | REALIDADE MISTA | EDGE AI | GOVERNANÇA | SAC MULTIMODAL | SEGURANÇA | ROBÓTICA",
      "summary": "Resumo executivo de 2 a 3 frases com dados concretos da matéria",
      "impact_b2b": "Por que isso importa para diretores e VPs B2B",
      "suggested_topic": "Tema estratégico pronto para gerar post no LinkedIn"
    }}
  ]
}}
"""
            raw = self._generate_with_search(prompt, temperature=0.95)
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed_trends = []
            if json_match:
                try:
                    res = json.loads(json_match.group())
                    parsed_trends = res.get("trends", [])
                except Exception as e:
                    print(f"Erro no parse de JSON do radar: {e}")

            # 3. Grava no banco de dados SQLite (evitando duplicatas pelo título)
            if not parsed_trends:
                parsed_trends = [
                    {
                        "title": f"Edge AI na Conformidade NR-12 (Varredura {timestamp_seed})",
                        "category": "EDGE AI & SEGURANÇA",
                        "summary": "Fábricas estão implantando análise local de câmeras para interrupção instantânea de máquinas ao detectar invasão de área de risco.",
                        "impact_b2b": "Zeragem de passivos trabalhistas e interrupção imediata de acidentes graves em tempo real.",
                        "suggested_topic": "Como a Visão Computacional na Borda (Edge AI) está revolucionando a segurança industrial e a NR-12"
                    },
                    {
                        "title": f"Visão Agro-Industrial Preditiva em Lavouras ({timestamp_seed})",
                        "category": "VISÃO AGRO",
                        "summary": "Algoritmos de visão computacional em drones e câmeras de campo identificam pragas 14 dias antes da perda de safra.",
                        "impact_b2b": "Aumento médio de +15% na produtividade e redução de 30% no uso de defensivos agrícolas.",
                        "suggested_topic": "Inteligência Artificial no campo: identificando pragas e falhas de plantio antes que afetem a safra"
                    },
                    {
                        "title": f"Meta Quest 3 no Treinamento Corporativo de Alto Risco ({timestamp_seed})",
                        "category": "REALIDADE MISTA & EDTECH",
                        "summary": "Simuladores imersivos em VR multi-usuário elevam a retenção de aprendizado de 20% para 80% em treinamentos técnicos complexos.",
                        "impact_b2b": "Redução drástica do custo de logística presencial e eliminação de acidentes em ambiente simulação.",
                        "suggested_topic": "Por que grandes corporações estão adotando treinamentos em Realidade Mista (VR) para equipes de operação"
                    },
                    {
                        "title": f"SAC Multimodal com Memória de Contexto e Voz Humana ({timestamp_seed})",
                        "category": "ATENDIMENTO MULTIMODAL",
                        "summary": "Assistentes de voz inteligentes que analisam áudio, imagem e histórico do cliente em tempo real elevam a precisão a 95%.",
                        "impact_b2b": "Redução drástica do tempo médio de atendimento (TMA) e retenção imediata de clientes B2B.",
                        "suggested_topic": "O fim das URAs tradicionais: como a IA Multimodal de voz transforma a experiência do cliente corporativo"
                    },
                    {
                        "title": f"Governança C-Level & Radar Automático de Concorrência ({timestamp_seed})",
                        "category": "GOVERNANÇA CORPORATIVA",
                        "summary": "Painéis executivos movidos a IA varrem movimentos de mercado e relatórios estratégicos de concorrentes continuamente.",
                        "impact_b2b": "Tomada de decisão estratégica baseada em dados frescos em vez de relatórios trimestrais desatualizados.",
                        "suggested_topic": "Governança Inteligente: como VPs e C-Levels usam inteligência artificial para antecipar movimentos de mercado"
                    },
                    {
                        "title": f"Automação de Mídia Corporativa de Alto Impacto ({timestamp_seed})",
                        "category": "GERAÇÃO DE CONTEÚDO",
                        "summary": "Corporações estão usando motores generativos para acelerar a criação de apresentações comerciais e mídia institucional.",
                        "impact_b2b": "Gargalo de comunicação resolvido com retenção rigorosa da identidade de marca e agilidade de vendas.",
                        "suggested_topic": "Do briefing ao lançamento em 48h: como a automação de mídia transforma o marketing B2B"
                    }
                ]

            for t in parsed_trends:
                title = t.get("title", "").strip()
                if not title:
                    continue
                exists = db.query(WebTrendItem).filter(WebTrendItem.title == title).first()
                if not exists:
                    trend_obj = WebTrendItem(
                        title=title,
                        category=t.get("category", "INOVAÇÃO B2B"),
                        summary=t.get("summary", ""),
                        impact_b2b=t.get("impact_b2b", ""),
                        suggested_topic=t.get("suggested_topic", title),
                        used=False
                    )
                    db.add(trend_obj)
            db.commit()

            # 4. Retorna uma amostragem aleatória dos itens não usados gravados no banco
            q_active = db.query(WebTrendItem).filter(WebTrendItem.used == False)
            if query:
                q_active = q_active.filter(WebTrendItem.title.ilike(f"%{query}%") | WebTrendItem.summary.ilike(f"%{query}%") | WebTrendItem.category.ilike(f"%{query}%"))

            active_items = q_active.order_by(func.random()).limit(12).all()
            if active_items:
                return {
                    "trends": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "category": item.category,
                            "summary": item.summary,
                            "impact_b2b": item.impact_b2b,
                            "suggested_topic": item.suggested_topic,
                            "used": item.used
                        }
                        for item in active_items
                    ]
                }
        except Exception as e:
            print(f"Erro em fetch_web_trends: {e}")
        finally:
            db.close()

        return {"trends": []}

    def mark_trend_used(self, trend_id: int = None, topic: str = None) -> bool:
        """Marca uma tendência como usada (used = True) no banco de dados SQLite para ocultá-la de futuras listagens."""
        from database import SessionLocal, WebTrendItem
        db = SessionLocal()
        try:
            item = None
            if trend_id:
                item = db.query(WebTrendItem).filter(WebTrendItem.id == trend_id).first()
            if not item and topic:
                snippet = topic.strip()[:20]
                item = db.query(WebTrendItem).filter(
                    (WebTrendItem.suggested_topic.ilike(f"%{snippet}%")) | 
                    (WebTrendItem.title.ilike(f"%{snippet}%"))
                ).first()
                
            if item:
                item.used = True
                db.commit()
                print(f"Tendência ID {item.id} ('{item.title}') marcada como USADA (used=True).")
                return True
        except Exception as e:
            print(f"Erro ao marcar tendência como usada: {e}")
        finally:
            db.close()
        return False

    # ── 10. GERADOR DE CARROSSÉIS PDF PARA LINKEDIN ─────────────────────────────
    def generate_carousel_pdf(self, topic: str, slide_count: int = 5) -> dict:
        """Gera um roteiro em slides e compõe um arquivo PDF multi-slide corporativo para o LinkedIn."""
        import io, base64, html, json, re
        import cairosvg
        from pypdf import PdfWriter, PdfReader

        prompt = f"""
Você é o Diretor de Criação da VisionAI (visionai.com.br).
Crie um roteiro em {slide_count} slides para um Carrossel no LinkedIn sobre o tema: "{topic}".

Evolução dos Slides:
- Slide 1: Capa (Manchete Provocativa Clickbait B2B + Subtítulo)
- Slide 2: O Problema/Dor Atual da Indústria
- Slide 3: A Virada de Chave / Arquitetura VisionAI
- Slide 4: Métricas Reais de Impacto & ROI
- Slide 5: Conclusão & Chamada para Ação (CTA)

Responda APENAS com JSON:
{{
  "title": "Título Geral do Carrossel",
  "slides": [
    {{
      "slide_number": 1,
      "badge": "CATEGORIA B2B",
      "headline": "Manchete Principal do Slide",
      "body": "Texto curto explicativo ou métrica"
    }}
  ]
}}
"""
        raw = self._generate(prompt, temperature=0.7)
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        slides_data = []
        carousel_title = topic
        if json_match:
            try:
                data = json.loads(json_match.group())
                slides_data = data.get("slides", [])
                carousel_title = data.get("title", topic)
            except Exception:
                pass

        if not slides_data:
            slides_data = [
                {"slide_number": 1, "badge": "VISIONAI INSIGHTS", "headline": topic[:45], "body": "Como a tecnologia na borda está transformando as operações B2B."},
                {"slide_number": 2, "badge": "O DESAFIO", "headline": "Por Que o Modelo Antigo Falha?", "body": "Latência de rede e custos de nuvem inviabilizam análises em tempo real."},
                {"slide_number": 3, "badge": "A SOLUÇÃO", "headline": "Inteligência Local na Borda", "body": "Processamento de vídeo a 30 FPS diretamente nas câmeras existentes."},
                {"slide_number": 4, "badge": "RESULTADOS", "headline": "Métricas Reais de ROI", "body": "Eliminação de acidentes e +15% de produtividade no primeiro trimestre."},
                {"slide_number": 5, "badge": "PRÓXIMOS PASSOS", "headline": "Transforme Sua Operação", "body": "Acesse visionai.com.br e agende uma demonstração com nossos especialistas."}
            ]

        logo_b64 = self._get_official_logo_b64()
        logo_tag = f'<image href="data:image/png;base64,{logo_b64}" x="80" y="70" width="50" height="50"/>' if logo_b64 else '<rect x="80" y="70" width="50" height="50" rx="12" fill="url(#vision-grad)"/>'

        writer = PdfWriter()
        total_slides = len(slides_data)

        for s in slides_data:
            s_num = s.get("slide_number", 1)
            badge = html.escape(str(s.get("badge", "VISIONAI")).upper())
            headline = html.escape(str(s.get("headline", "")))
            body = html.escape(str(s.get("body", "")))

            def wrap_svg_text(txt: str, max_chars: int = 24, start_x: int = 80, start_y: int = 420, dy: int = 70, font_size: int = 56, fill_color: str = "#ffffff") -> str:
                words = txt.split()
                lines = []
                curr = []
                c_len = 0
                for w in words:
                    if c_len + len(w) + 1 > max_chars and curr:
                        lines.append(" ".join(curr))
                        curr = [w]
                        c_len = len(w)
                    else:
                        curr.append(w)
                        c_len += len(w) + 1
                if curr:
                    lines.append(" ".join(curr))
                
                tspans = []
                for i, line in enumerate(lines[:4]):
                    y_pos = start_y + (i * dy)
                    tspans.append(f'<text x="{start_x}" y="{y_pos}" font-family="\'Outfit\', \'Inter\', sans-serif" font-weight="800" font-size="{font_size}" fill="{fill_color}">{line}</text>')
                return "\n".join(tspans)

            headline_svg = wrap_svg_text(headline, max_chars=22, start_x=80, start_y=380, dy=68, font_size=54, fill_color="#ffffff")
            body_svg = wrap_svg_text(body, max_chars=38, start_x=80, start_y=720, dy=42, font_size=28, fill_color="#94a3b8")

            svg_slide = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">
  <defs>
    <linearGradient id="bg-grad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#050505"/>
      <stop offset="50%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#050505"/>
    </linearGradient>
    <linearGradient id="vision-grad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#9EFF00"/>
      <stop offset="100%" stop-color="#0055FF"/>
    </linearGradient>
  </defs>

  <rect width="1080" height="1080" fill="url(#bg-grad)"/>
  <circle cx="950" cy="150" r="300" fill="#9EFF00" opacity="0.08"/>
  <circle cx="150" cy="950" r="350" fill="#0055FF" opacity="0.10"/>

  <g transform="translate(80, 70)">
    {logo_tag}
    <text x="64" y="36" font-family="'Outfit', sans-serif" font-weight="900" font-size="28" fill="#ffffff">VISION<tspan fill="#9EFF00">AI</tspan></text>
    <text x="220" y="36" font-family="'Inter', sans-serif" font-weight="400" font-size="16" fill="#94a3b8">| Corporate Tech</text>
  </g>

  <g transform="translate(780, 75)">
    <rect width="220" height="40" rx="20" fill="rgba(158,255,0,0.15)" stroke="rgba(158,255,0,0.5)" stroke-width="1.5"/>
    <text x="110" y="26" font-family="'Inter', sans-serif" font-weight="800" font-size="13" fill="#9EFF00" text-anchor="middle" letter-spacing="1">{badge}</text>
  </g>

  {headline_svg}
  <rect x="80" y="650" width="160" height="6" rx="3" fill="url(#vision-grad)"/>
  {body_svg}

  <g transform="translate(80, 980)">
    <text x="0" y="0" font-family="'Inter', sans-serif" font-weight="600" font-size="18" fill="#64748b">Inovação B2B ✦ visionai.com.br</text>
    <text x="920" y="0" font-family="'Inter', sans-serif" font-weight="800" font-size="18" fill="#9EFF00" text-anchor="end">Slide {s_num}/{total_slides}</text>
  </g>
</svg>"""

            pdf_page_bytes = cairosvg.svg2pdf(bytestring=svg_slide.encode('utf-8'))
            reader = PdfReader(io.BytesIO(pdf_page_bytes))
            writer.add_page(reader.pages[0])

        out_pdf_buf = io.BytesIO()
        writer.write(out_pdf_buf)
        pdf_bytes = out_pdf_buf.getvalue()
        pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

        return {
            "title": carousel_title,
            "slides_count": total_slides,
            "pdf_base64": pdf_b64,
            "pdf_mime": "application/pdf"
        }

    # ── 11. EXTRAÇÃO & TRANSFORMAÇÃO DE DOCUMENTOS ─────────────────────────────
    def parse_document_to_posts(self, document_text: str) -> dict:
        """Converte o conteúdo textual de um documento/PDF interno em uma série de 3 a 5 posts B2B."""
        prompt = f"""
Você é o Diretor de Conteúdo B2B da VisionAI (visionai.com.br).

DOCUMENTO INTERNO FORNECIDO:
---
{document_text[:4000]}
---

SUA TAREFA:
Analise este documento corporativo e desmembre-o em 3 posts de alto impacto para o LinkedIn.

Responda APENAS com JSON:
{{
  "document_summary": "Resumo executivo do documento em 2 frases",
  "generated_posts": [
    {{
      "post_number": 1,
      "topic": "Tema central do post",
      "angle": "Ângulo (ex: ROI, Estudo de Caso, Provocação)",
      "content": "Texto completo do post em Português com hashtags"
    }}
  ]
}}
"""
        raw = self._generate(prompt, temperature=0.7)
        import re, json
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                res = json.loads(json_match.group())
                for post in res.get("generated_posts", []):
                    if post.get("content"):
                        clean_text, _ = self._clean_post_content(post["content"])
                        post["content"] = clean_text
                return res
            except Exception as e:
                print(f"Erro no parse_document_to_posts: {e}")
        return {"document_summary": "Documento processado com sucesso", "generated_posts": []}
