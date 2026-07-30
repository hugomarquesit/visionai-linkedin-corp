import os
import json
import requests
import base64
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from database import SessionLocal, ScrapedKnowledge

TEXT_MODEL = "gemini-3.5-flash"
IMAGE_MODEL = "gemini-3.1-flash-image"

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
        self.fallback_models = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.1-pro-preview", "gemini-2.5-flash"]
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
                err_str = str(e)
                if "404" in err_str or "NOT_FOUND" in err_str or "model" in err_str.lower():
                    continue
                return f"[Erro Gemini: {err_str}]"
        return f"[Erro Gemini: Nenhum modelo disponível para a chave configurada]"

    def _generate_svg_banner(self, title: str, category: str = "VisionAi Insights") -> str:
        """Gera um banner SVG corporativo 1200x630 com branding VisionAi, HUD de computação visual e título em PT-BR."""
        # Clean title for SVG embedding - ensure PT-BR text
        first_line = title.strip().split("\n")[0]
        clean_first_line = first_line.replace("#", "").replace("**", "").strip()
        clean_title = (clean_first_line[:75] + "...") if len(clean_first_line) > 75 else clean_first_line
        clean_category = category.upper()
        
        svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070b14"/>
      <stop offset="50%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e1b4b"/>
    </linearGradient>
    <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="50%" stop-color="#818cf8"/>
      <stop offset="100%" stop-color="#c084fc"/>
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

  <!-- Background -->
  <rect width="1200" height="630" fill="url(#bg)"/>
  
  <!-- Glowing Orbs & AI Scan Grid -->
  <circle cx="150" cy="120" r="180" fill="#38bdf8" opacity="0.15" filter="url(#glow)"/>
  <circle cx="1050" cy="500" r="220" fill="#818cf8" opacity="0.18" filter="url(#glow)"/>
  
  <!-- Grid Lines -->
  <path d="M 0 150 L 1200 150 M 0 300 L 1200 300 M 0 450 L 1200 450" stroke="rgba(56, 189, 248, 0.05)" stroke-width="1"/>
  <path d="M 300 0 L 300 630 M 600 0 L 600 630 M 900 0 L 900 630" stroke="rgba(56, 189, 248, 0.05)" stroke-width="1"/>

  <!-- Computer Vision Bounding Box Overlay Simulation (HUD) -->
  <g opacity="0.4">
    <!-- Camera Bounding Box Top Right -->
    <path d="M 980 160 L 1020 160 M 980 160 L 980 200" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <path d="M 1120 160 L 1080 160 M 1120 160 L 1120 200" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <path d="M 980 280 L 1020 280 M 980 280 L 980 240" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <path d="M 1120 280 L 1080 280 M 1120 280 L 1120 240" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <rect x="980" y="140" width="140" height="18" fill="rgba(56, 189, 248, 0.2)" rx="2"/>
    <text x="985" y="153" font-family="'Inter', monospace" font-size="10" fill="#38bdf8" font-weight="700">AI DETECT: 99.8%</text>

    <!-- Camera Reticle Bottom Left -->
    <circle cx="150" cy="480" r="24" stroke="#34d399" stroke-width="1.5" stroke-dasharray="4 4" fill="none"/>
    <text x="185" y="484" font-family="'Inter', monospace" font-size="11" fill="#34d399" font-weight="600">[ EDGE NODE 01: COMPLIANT ]</text>
  </g>

  <!-- Glass Card Container -->
  <rect x="80" y="80" width="1040" height="470" rx="24" fill="url(#card-bg)" stroke="rgba(56,189,248,0.2)" stroke-width="1.5"/>
  
  <!-- Top Bar: Logo & Badge -->
  <g transform="translate(130, 130)">
    <!-- Logo Icon -->
    <rect width="48" height="48" rx="12" fill="url(#accent)"/>
    <text x="24" y="32" font-family="'Inter', sans-serif" font-weight="800" font-size="24" fill="#ffffff" text-anchor="middle">V</text>
    <!-- Brand Name -->
    <text x="64" y="32" font-family="'Inter', sans-serif" font-weight="700" font-size="24" fill="#ffffff" letter-spacing="-0.5">VisionAi</text>
    <text x="165" y="32" font-family="'Inter', sans-serif" font-weight="400" font-size="14" fill="#94a3b8">| Corporate Tech</text>
  </g>
  
  <!-- Category Badge -->
  <g transform="translate(900, 135)">
    <rect width="170" height="34" rx="17" fill="rgba(56, 189, 248, 0.15)" stroke="rgba(56, 189, 248, 0.4)" stroke-width="1"/>
    <text x="85" y="22" font-family="'Inter', sans-serif" font-weight="600" font-size="12" fill="#38bdf8" text-anchor="middle" letter-spacing="1">{clean_category}</text>
  </g>

  <!-- Main Headline in PT-BR -->
  <foreignObject x="130" y="210" width="940" height="220">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: 'Outfit', 'Inter', system-ui, sans-serif; color: #f8fafc; font-size: 42px; font-weight: 700; line-height: 1.25; letter-spacing: -1px; text-shadow: 0 4px 12px rgba(0,0,0,0.5);">
      {clean_title}
    </div>
  </foreignObject>

  <!-- Accent Line -->
  <rect x="130" y="460" width="120" height="4" rx="2" fill="url(#accent)"/>

  <!-- Footer Info in PT-BR -->
  <text x="130" y="500" font-family="'Inter', sans-serif" font-weight="500" font-size="16" fill="#94a3b8">Inovação, Inteligência Artificial &amp; Computação na Borda</text>
  <text x="1070" y="500" font-family="'Inter', sans-serif" font-weight="600" font-size="15" fill="#38bdf8" text-anchor="end">visionai.com.br ✦</text>
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
        Combina a foto realista gerada por IA com a Moldura Publicitária da VisionAI (Peça Publicitária de Agência).
        Cria um criativo publicitário 1200x630 profissional em JPEG de alta resolução.
        """
        import io
        from PIL import Image
        import cairosvg

        try:
            # 1. Carrega e redimensiona a foto de fundo para 1200x630
            bg = Image.open(io.BytesIO(raw_img_bytes)).convert("RGB")
            bg = bg.resize((1200, 630), Image.Resampling.LANCZOS)

            # 2. Formata manchete em PT-BR para o SVG overlay
            first_line = pt_headline.strip().split("\n")[0]
            clean_first_line = first_line.replace("#", "").replace("**", "").strip()
            clean_title = (clean_first_line[:75] + "...") if len(clean_first_line) > 75 else clean_first_line
            clean_category = category.upper()

            # 3. Cria a moldura de design gráfico publicitário (SVG com gradiente escuro, marca VisionAI e badges)
            svg_overlay = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="grad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#6366f1"/>
    </linearGradient>
    <linearGradient id="shadow" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="rgba(7,11,20,0.88)"/>
      <stop offset="60%" stop-color="rgba(7,11,20,0.45)"/>
      <stop offset="100%" stop-color="rgba(7,11,20,0.25)"/>
    </linearGradient>
  </defs>

  <!-- Gradiente de escurecimento para legibilidade perfeita do texto -->
  <rect width="1200" height="630" fill="url(#shadow)"/>

  <!-- HUD Telemetria Visão Computacional -->
  <g opacity="0.6">
    <path d="M 950 140 L 980 140 M 950 140 L 950 170" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <path d="M 1080 140 L 1050 140 M 1080 140 L 1080 170" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <path d="M 950 240 L 980 240 M 950 240 L 950 210" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <path d="M 1080 240 L 1050 240 M 1080 240 L 1080 210" stroke="#38bdf8" stroke-width="2" fill="none"/>
    <rect x="950" y="122" width="130" height="16" fill="rgba(56, 189, 248, 0.25)" rx="2"/>
    <text x="955" y="134" font-family="'Inter', monospace" font-size="10" fill="#38bdf8" font-weight="bold">AI DETECT: 99.8%</text>
  </g>

  <!-- Cabeçalho: Logo VisionAI & Branding -->
  <g transform="translate(80, 60)">
    <rect width="44" height="44" rx="10" fill="url(#grad)"/>
    <text x="22" y="30" font-family="'Inter', sans-serif" font-weight="bold" font-size="22" fill="#ffffff" text-anchor="middle">V</text>
    <text x="58" y="30" font-family="'Inter', sans-serif" font-weight="bold" font-size="22" fill="#ffffff">VisionAi</text>
    <text x="165" y="30" font-family="'Inter', sans-serif" font-size="14" fill="#94a3b8">| Corporate Tech</text>
  </g>

  <!-- Selo de Categoria -->
  <g transform="translate(940, 62)">
    <rect width="180" height="34" rx="17" fill="rgba(56, 189, 248, 0.18)" stroke="rgba(56, 189, 248, 0.5)" stroke-width="1"/>
    <text x="90" y="22" font-family="'Inter', sans-serif" font-weight="bold" font-size="11" fill="#38bdf8" text-anchor="middle">{clean_category}</text>
  </g>

  <!-- Título Principal do Criativo em PT-BR -->
  <foreignObject x="80" y="190" width="1040" height="280">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: 'Outfit', 'Inter', system-ui, sans-serif; color: #ffffff; font-size: 38px; font-weight: 800; line-height: 1.3; text-shadow: 0 4px 16px rgba(0,0,0,0.9);">
      {clean_title}
    </div>
  </foreignObject>

  <!-- Rodapé Publicitário -->
  <rect x="80" y="540" width="100" height="3" rx="1.5" fill="url(#grad)"/>
  <text x="80" y="575" font-family="'Inter', sans-serif" font-weight="500" font-size="14" fill="#94a3b8">Inovação, Inteligência Artificial &amp; Computação na Borda</text>
  <text x="1120" y="575" font-family="'Inter', sans-serif" font-weight="bold" font-size="14" fill="#38bdf8" text-anchor="end">visionai.com.br ✦</text>
</svg>"""

            # 4. Renderiza moldura e faz composição alfa sobre a foto
            overlay_png = cairosvg.svg2png(bytestring=svg_overlay.encode('utf-8'))
            overlay_img = Image.open(io.BytesIO(overlay_png)).convert('RGBA')

            composite = Image.alpha_composite(bg.convert('RGBA'), overlay_img)
            out = io.BytesIO()
            composite.convert('RGB').save(out, format='JPEG', quality=95)
            
            img_b64 = base64.b64encode(out.getvalue()).decode('utf-8')
            print("Peça publicitária corporativa (foto + moldura de design) criada com sucesso!")
            return img_b64, "image/jpeg"
        except Exception as e:
            print(f"Erro ao compor peça publicitária: {e} — usando foto original")
            img_b64 = base64.b64encode(raw_img_bytes).decode('utf-8')
            return img_b64, "image/jpeg"

    def _generate_image_base64(self, prompt: str, pt_title: str = "VisionAI Insights") -> tuple[str, str]:
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
                        return self._composite_advertising_creative(img_bytes, pt_headline=pt_title)
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
                            return self._composite_advertising_creative(img_bytes, pt_headline=pt_title)
            except Exception as e:
                print(f"Modelo de imagem {model} falhou: {e}")
                continue

        # Fallback: SVG corporativo VisionAI com título em Português (PT-BR)
        print("Usando banner SVG corporativo como fallback visual com título em Português.")
        svg_b64 = self._generate_svg_banner(title=pt_title)
        return svg_b64, "image/svg+xml"

    def regenerate_media_from_revised_text(self, revised_text: str, media_type: str = "image") -> dict:
        """
        Recebe o texto editado pelo usuário e gera uma nova peça visual (imagem ou banner)
        que representa fielmente a versão final revisada pelo usuário.
        """
        prompt = f"""
Você é o Diretor de Fotografia Corporativa Sênior da VisionAI (visionai.com.br).

TEXTO FINAL DO POST NO LINKEDIN:
---
{revised_text[:1500]}
---

Sua tarefa: Crie um prompt de imagem em INGLÊS para gerar UMA FOTOGRAFIA CORPORATIVA 100% REALISTA E PRÁTICA da aplicação descrita no texto acima.

REGRAS RÍGIDAS DE FOTOGRAFIA REALISTA (SEM FUTURISMO EXAGERADO OU SCI-FI):
1. FOTOGRAFIA REALISTA: Crie um prompt para uma FOTO CORPORATIVA/INDUSTRIAL REALISTA (ex: foto tirada com câmera profissional 35mm, iluminação natural de fábrica ou escritório, operadores de fábrica reais trabalhando com capacetes e coletes refletivos, câmeras de segurança CCTV reais no teto da fábrica, drones agrícolas reais sobrevoando lavouras de milho/soja).
2. PROIBIDO ELEMENTOS FUTURISTAS/SCI-FI: NUNCA crie portais cibernéticos, luzes laser de ficção científica ou néons brilhantes irreais. A imagem deve parecer uma fotografia real de capa da Forbes ou Harvard Business Review.
3. SEM TEXTO EM PIXELS: NUNCA coloque títulos ou palavras no prompt da imagem.
4. ADICIONE NO FINAL DO PROMPT: 'authentic realistic professional corporate photography, Hasselblad medium format camera, natural office or factory lighting, sharp focus, 8k resolution, NO sci-fi, NO text, NO letters, NO typography'.

Responda APENAS com JSON:
{{"image_prompt": "prompt de fotografia realista em inglês aqui"}}
"""
        raw = self._generate(prompt, temperature=0.7)
        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        image_prompt = ""
        if json_match:
            try:
                data = json.loads(json_match.group())
                image_prompt = data.get("image_prompt", "")
            except Exception:
                pass
        
        if not image_prompt:
            image_prompt = f"Corporate tech 3D render representing: {revised_text[:100]}"
            
        pt_headline = revised_text.strip().split("\n")[0]
        img_b64, mime = self._generate_image_base64(image_prompt, pt_title=pt_headline)
        return {
            "image_prompt": image_prompt,
            "image_base64": img_b64,
            "image_mime": mime,
            "media_type": media_type
        }

    # ── 1. GERAÇÃO DE POSTS ────────────────────────────────────────────────────
    def generate_post(self, topic: str, format_type: str = "standard", tone: str = "visionario") -> dict:
        """Gera um post completo usando um fluxo estritamente sequencial em 2 etapas:
           ETAPA 1: Criação do texto final do post.
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

        # ── ETAPA 1: GERAÇÃO DO TEXTO DO POST ──────────────────────────────────
        text_prompt = f"""
Você é o VP de Engenharia de Operações & CCO da VisionAI (visionai.com.br).

CONTEXTO INSTITUCIONAL E TÉCNICO DA VISIONAI:
{ORG_CONTEXT}
{self.scraped_context}

SUA MISSÃO: Escrever um post de altíssimo valor executivo para o LinkedIn Corporativo sobre o tema abaixo.

TEMA/OBJETIVO: {topic}
FORMATO DE CONTEÚDO: {format_guides.get(format_type, format_guides['standard'])}
TOM DE VOZ: {tone_guides.get(tone, tone_guides['visionario'])}

PROIBIDO CLICHÊS DE IA & ESTILO ARTIFICIAL (REGRAS CRÍTICAS):
- PROIBIDO usar introduções genéricas ou clichês como: "No mundo de hoje", "Em um cenário dinâmico/competitivo", "Na era da Inteligência Artificial", "Em constante evolução", "Em suma", "Vamos juntos", "Desbloquear o potencial", "Revolucionar a forma", "Impulsionar o futuro".
- PROIBIDO parecer um folheto publicitário raso. Escreva como um CTO ou VP de Operações real falando pragmaticamente de engenharia e negócios com diretores executivos (C-Level).
- Aborde DORES OPERACIONAIS REAIS: latência de streaming RTSP, estouro de orçamento de banda/nuvem, processamento Edge AI a 30 FPS nas câmeras que a fábrica já possui, fiscalização 24/7 de EPIs sem humanos na sala de controle, passivo trabalhista, retenção 4x maior em VR, LGPD.
- Parágrafos curtos, subtítulos com emojis elegantes e frases diretas.
- Inclua métricas e resultados concretos (+15% produtividade no agro, 95% precisão em atendimento, retenção 4x em VR, ciclo de vídeo de 3 semanas para 2 dias).
- Termine com 3 a 5 hashtags corporativas estratégicas (ex: #VisaoComputacional #EdgeAI #InteligenciaArtificial #InovacaoCorporativa #VisionAI).

FORMATO DE SAÍDA: Retorne APENAS o texto completo e formatado do post em português.
"""
        post_text = self._generate(text_prompt, temperature=0.85).strip()
        if post_text.startswith("```"):
            post_text = "\n".join(post_text.split("\n")[1:]).rstrip("`").strip()

        # ── ETAPA 2: GERAÇÃO DA ARTE VISUAL BASEADA NO TEXTO CRIADO ──────────────
        # O prompt visual e a imagem são criados APÓS o texto existir, com 100% de alinhamento com o seu significado!
        art_result = self.regenerate_media_from_revised_text(post_text, media_type="image")
        
        image_prompt = art_result.get("image_prompt", "")
        image_b64 = art_result.get("image_base64", "")
        image_mime = art_result.get("image_mime", "image/svg+xml")

        return {
            "topic": topic,
            "format": format_type,
            "tone": tone,
            "content": post_text,
            "image_prompt": image_prompt,
            "image_base64": image_b64,
            "image_mime": image_mime,
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
        return [t.strip() for t in raw.split(",") if "#" in t]
