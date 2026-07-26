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
        self.client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
        self.model = TEXT_MODEL
        self.fallback_models = ["gemini-3.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        self.scraped_context = self._scrape_visionai_website()

    def _scrape_visionai_website(self) -> str:
        """Scrape do bundle JS da SPA visionai.com.br para extrair conteúdo real dos serviços."""
        import re
        db = SessionLocal()
        try:
            # Cache: se já foi feito scraping recente (< 24h), usa do banco
            knowledge = db.query(ScrapedKnowledge).filter_by(category="institucional_v2").first()
            if knowledge and knowledge.content and len(knowledge.content) > 200:
                return f"\n\nCONTEÚDO DO SITE VISIONAI.COM.BR:\n{knowledge.content}"
            
            # Pega o HTML para descobrir o bundle JS
            home_resp = requests.get("https://visionai.com.br", timeout=10)
            js_urls = re.findall(r'/assets/[^"]+\.js', home_resp.text)
            
            extracted = []
            for js_path in js_urls[:2]:  # máx 2 bundles
                try:
                    js_resp = requests.get(f"https://visionai.com.br{js_path}", timeout=15)
                    content = js_resp.text
                    # Extrai strings em PT-BR com conteúdo real
                    strings = re.findall(r'"([^"\\]{15,300})"', content)
                    pt_chars = 'áéíóúãõâêôçàèìòùÁÉÍÓÚÃÕÂÊÔÇ'
                    pt_words = ['visão','inteligên','solução','análise','dados','monitoramento',
                                'drone','câmera','automação','educação','empresa','processo',
                                'resultado','tecnologia','document','identificamos','automatiz',
                                'negócio','cliente','risco','operação','imagem','vídeo','áudio',
                                'computação','nuvem','segurança','gestão','relatório','inspeção',
                                'agrícola','industrial','treinamento','realidade','mista','borda',
                                'detecção','monitoram','precisão','produtividade']
                    seen = set()
                    for t in strings:
                        t = t.strip()
                        if t in seen or t.startswith('http') or len(t) < 20:
                            continue
                        has_pt = any(c in t for c in pt_chars) or any(w.lower() in t.lower() for w in pt_words)
                        if has_pt:
                            seen.add(t)
                            extracted.append(t)
                except Exception:
                    continue
            
            if extracted:
                text = "\n".join(extracted[:80])  # limita para não explodir o contexto
                # Salva no banco
                if knowledge:
                    knowledge.content = text
                else:
                    db.add(ScrapedKnowledge(category="institucional_v2", url="https://visionai.com.br", content=text))
                db.commit()
                return f"\n\nCONTEÚDO DO SITE VISIONAI.COM.BR:\n{text}"
        except Exception as e:
            print(f"Erro no scraping do site: {e}")
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
        """Gera um banner SVG corporativo 1200x630 com branding VisionAi e retorna em Base64."""
        # Clean title for SVG embedding
        clean_title = (title[:65] + "...") if len(title) > 65 else title
        clean_category = category.upper()
        
        svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0a0d14"/>
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
  
  <!-- Glowing Orbs -->
  <circle cx="150" cy="120" r="180" fill="#38bdf8" opacity="0.15" filter="url(#glow)"/>
  <circle cx="1050" cy="500" r="220" fill="#818cf8" opacity="0.18" filter="url(#glow)"/>
  
  <!-- Grid Lines -->
  <path d="M 0 150 L 1200 150 M 0 300 L 1200 300 M 0 450 L 1200 450" stroke="rgba(255,255,255,0.03)" stroke-width="1"/>
  <path d="M 300 0 L 300 630 M 600 0 L 600 630 M 900 0 L 900 630" stroke="rgba(255,255,255,0.03)" stroke-width="1"/>

  <!-- Glass Card Container -->
  <rect x="80" y="80" width="1040" height="470" rx="24" fill="url(#card-bg)" stroke="rgba(255,255,255,0.12)" stroke-width="1.5"/>
  
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

  <!-- Main Headline -->
  <foreignObject x="130" y="210" width="940" height="220">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: 'Inter', system-ui, sans-serif; color: #f8fafc; font-size: 42px; font-weight: 700; line-height: 1.25; letter-spacing: -1px; text-shadow: 0 4px 12px rgba(0,0,0,0.5);">
      {clean_title}
    </div>
  </foreignObject>

  <!-- Accent Line -->
  <rect x="130" y="460" width="120" height="4" rx="2" fill="url(#accent)"/>

  <!-- Footer Info -->
  <text x="130" y="500" font-family="'Inter', sans-serif" font-weight="500" font-size="16" fill="#94a3b8">Inovação, IA &amp; Transformação Digital Corporativa</text>
  <text x="1070" y="500" font-family="'Inter', sans-serif" font-weight="600" font-size="15" fill="#38bdf8" text-anchor="end">visionai.com.br ✦</text>
</svg>"""
        return base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')

    def get_auto_topics(self) -> list:
        """Gera 12 tópicos cobrindo todos os serviços reais do site visionai.com.br via Gemini."""
        import re as _re
        site_content = self.scraped_context or ""

        prompt = f"""
Você é um estrategista de conteúdo LinkedIn B2B para a empresa VisionAI.

INFORMAÇÕES DA EMPRESA:
{ORG_CONTEXT}

CONTEÚDO REAL EXTRAÍDO DO SITE (visionai.com.br):
{site_content[:3000]}

Gere EXATAMENTE 12 ideias de posts, 2 por linha de serviço abaixo (cubra TODAS):
1. Visão Computacional & Edge — câmeras existentes, EPI, rastreamento, mapas de calor
2. IA Multimodal & Atendimento — áudio+vídeo+imagem simultâneos, voz com contexto, URA
3. Realidade Mista & EdTech — VR/Meta Quest 3, simulação de riscos, neurodiversidade
4. Visão Agro-Industrial — drones, detecção de pragas, manutenção preditiva Edge AI
5. Geração de Conteúdo & Analytics — automação de vídeos, apresentações automáticas
6. Governança Corporativa & Intelligence — portais, inteligência competitiva

REGRAS ABSOLUTAS:
- NUNCA mencionar SAP em nenhum tópico
- NUNCA mencionar Cloud genérico ou Soberania de Dados
- Use dados reais: +15% produtividade agro, 95% precisão atendimento, 3sem→2dias, 4x retenção VR
- Público: C-Levels, Gestores Industriais, Diretores de TI

Responda APENAS com JSON válido, sem markdown:
[{{"topic": "...", "category": "...", "format": "...", "tone": "..."}}]
"""

        try:
            raw = self._generate(prompt, temperature=0.85)
            json_match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
            if json_match:
                topics = json.loads(json_match.group())
                if isinstance(topics, list) and len(topics) > 0:
                    return topics[:12]
        except Exception as e:
            print(f"Erro ao gerar tópicos via Gemini: {e}")

        # Fallback rico: 12 tópicos cobrindo TODAS as 6 linhas de serviço reais da VisionAI
        return [
            {"topic": "As câmeras que você já tem instaladas podem fiscalizar EPIs 24h/dia — sem nenhum humano olhando. Isso já é realidade com Edge AI", "category": "Visão Computacional", "format": "insight", "tone": "direto"},
            {"topic": "Fluxo invisível no armazém? Rastreamos 100% dos ativos, veículos e pessoas em tempo real — sem nova infraestrutura, só IA nas câmeras existentes", "category": "Visão Computacional", "format": "case", "tone": "tecnico"},
            {"topic": "Seu cliente envia foto + áudio + documento. Nossa IA analisa tudo em segundos com 95% de precisão. Isso é atendimento multimodal real", "category": "IA Multimodal", "format": "educativo", "tone": "tecnico"},
            {"topic": "URA que perde o fio quando o usuário muda de assunto? Criamos assistentes de voz com memória de contexto que executam ações em tempo real", "category": "IA Multimodal", "format": "provocativo", "tone": "provocativo"},
            {"topic": "No Meta Quest 3, simulamos cenários de risco real onde o erro não tem consequência — retenção 4x mais eficaz que treinamento convencional", "category": "Realidade Mista & EdTech", "format": "case", "tone": "inspirador"},
            {"topic": "Como treinar líderes para neurodiversidade? Criamos ambiente VR que simula como uma pessoa neurodiversa percebe o mundo. Empatia que se aprende na prática", "category": "Realidade Mista & EdTech", "format": "storytelling", "tone": "visionario"},
            {"topic": "Perdas de safra por identificação tardia de pragas. Detectamos anomalias dias antes de serem visíveis a olho nu — +15% produtividade, menos defensivos", "category": "Agro & Industrial", "format": "case", "tone": "inspirador"},
            {"topic": "Máquinas parando sem aviso em produção? Identificamos desgaste no hardware local, sem depender de nuvem. Manutenção preditiva onde não chega internet", "category": "Agro & Industrial", "format": "insight", "tone": "direto"},
            {"topic": "Produção de vídeo institucional: 3 semanas de trabalho → 2 dias com automação IA. Roteiro, narração e edição. Custo 70% menor, qualidade superior", "category": "Geração de Conteúdo", "format": "storytelling", "tone": "visionario"},
            {"topic": "Propostas genéricas não fecham negócio. Geramos apresentações personalizadas por segmento de cliente de forma automática — para o decisor certo, na hora certa", "category": "Geração de Conteúdo", "format": "lista", "tone": "direto"},
            {"topic": "Sua equipe gasta horas coletando dados de concorrentes manualmente? Automatizamos a análise competitiva — relatórios de inteligência em minutos, não dias", "category": "Governança & Intelligence", "format": "lista", "tone": "provocativo"},
            {"topic": "Site institucional que não passa credibilidade afasta decisores antes do primeiro contato. Construímos portais corporativos otimizados para o público certo", "category": "Governança & Intelligence", "format": "insight", "tone": "educativo"},
        ]

    def _generate_image_base64(self, prompt: str) -> str:
        """Gera uma imagem a partir de um prompt e retorna em Base64 usando o modelo de imagem configurado."""
        try:
            res = self.client.models.generate_images(
                model="imagen-3.0-generate-001",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/jpeg",
                    aspect_ratio="1:1"
                )
            )
            for img in res.generated_images:
                return base64.b64encode(img.image.image_bytes).decode('utf-8')
        except Exception as e:
            print(f"API de imagem indisponível ({e}). Gerando banner SVG corporativo VisionAi como fallback visual...")
            return self._generate_svg_banner(prompt)
        return ""

    # ── 1. GERAÇÃO DE POSTS ────────────────────────────────────────────────────
    def generate_post(self, topic: str, format_type: str = "standard", tone: str = "visionario") -> dict:
        """Gera um post completo para o LinkedIn corporativo usando frameworks avançados."""
        format_guides = {
            "standard": "Post de texto direto, 150-300 palavras, 3-5 hashtags relevantes.",
            "institucional": "Post sobre a cultura, visão e missão da VisionAI. Demonstre liderança corporativa, inovação sustentável e impacto no mercado LATAM. Termine com a visão de futuro.",
            "produto_pitch": "Framework PAS (Problem, Agitation, Solution). Identifique uma dor clara de C-levels (ex: dados espalhados, processos manuais), agite a dor com impacto negativo (perda de ROI) e apresente as soluções/produtos da VisionAI como a bala de prata.",
            "case_estudo": "Post focado em resultado (Estudo de Caso real ou simulado altamente verossímil). 1) O desafio crítico do cliente; 2) A solução técnica aplicada (IA/SAP/Cloud); 3) Métricas de impacto geradas (% ROI, horas ganhas).",
            "lideranca_tecnica": "Post aprofundado, focando na arquitetura, governança ou segurança. Use linguagem técnica robusta e aborde temas como Soberania de Dados e IA responsável."
        }

        tone_guides = {
            "visionario": "Tom visionário e desafiador — questione o status quo, provoque reflexão profunda",
            "tecnico": "Tom analítico e arquitetural, cite infraestrutura, metodologias ágeis e ROI",
            "inspirador": "Tom focado em cultura corporativa e Employer Branding, destacando o valor humano",
            "educativo": "Tom professoral e consultivo, educando o mercado sobre os benefícios de novas tecnologias",
        }

        prompt = f"""
Você é o redator sênior de LinkedIn da VisionAi e diretor de arte.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}
{self.scraped_context}

TAREFA: Crie um "Criativo Completo" para um post de LinkedIn sobre o seguinte tema:
TEMA: {topic}
FORMATO: {format_guides.get(format_type, format_guides['standard'])}
TOM: {tone_guides.get(tone, tone_guides['visionario'])}

REGRAS DO POST:
- Primeira linha deve ser um gancho poderoso
- Use emojis estrategicamente (máximo 5)
- Hashtags no final (3-5, relevantes e em português/inglês)
- Foque em valor real e insights acionáveis
- Termine com uma pergunta ou CTA que gere engajamento

REGRAS DO CRIATIVO (IMAGEM):
- Você DEVE sugerir um prompt visual hiper-detalhado (em inglês) para gerar a arte que acompanhará o post.
- Descreva a iluminação, estilo (ex: fotorealista, vetor, 3D render, cyberpunk, corporativo limpo), cores principais e elementos visuais.

FORMATO DE SAÍDA OBRIGATÓRIO:
Retorne APENAS um JSON válido contendo as chaves:
"post_text": "o texto do post aqui",
"image_prompt": "o prompt em inglês para o gerador de imagem aqui"
"""
        content_raw = self._generate(prompt, temperature=0.85)
        
        post_text = ""
        image_prompt = ""
        image_b64 = ""
        
        try:
            # Strip markdown code fences if model wrapped in ```json ... ```
            cleaned = content_raw.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:])
                cleaned = cleaned.rstrip("`").strip()

            # Find JSON object
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(cleaned[start:end])
                raw_post = data.get("post_text", "")
                # Properly unescape \\n -> real newlines
                if isinstance(raw_post, str):
                    post_text = raw_post.replace("\\n", "\n").strip()
                else:
                    post_text = str(raw_post)
                raw_img = data.get("image_prompt", "")
                image_prompt = raw_img.replace("\\n", " ").strip() if isinstance(raw_img, str) else ""

                # Generate image if we got a prompt
                if image_prompt:
                    image_b64 = self._generate_image_base64(image_prompt)
            else:
                post_text = content_raw
        except Exception as e:
            print(f"[GeminiStudio] JSON parse error: {e} — using raw content")
            post_text = content_raw

        return {
            "topic": topic,
            "format": format_type,
            "tone": tone,
            "content": post_text,
            "image_prompt": image_prompt,
            "image_base64": image_b64,
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
