"""
Script to generate a visual diagram of the LangGraph workflow structure.
Creates an SVG file directly without external dependencies.

Updated: Now includes evaluation, guardrails, human review gate, and publishing.
"""

import os


def create_graph_diagram():
    """Create a visual diagram of the LangGraph workflow as SVG."""

    svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="1000" height="1800" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333333" />
    </marker>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur in="SourceAlpha" stdDeviation="2"/>
      <feOffset dx="2" dy="2" result="offsetblur"/>
      <feComponentTransfer>
        <feFuncA type="linear" slope="0.3"/>
      </feComponentTransfer>
      <feMerge>
        <feMergeNode/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <!-- Title -->
  <text x="500" y="35" font-family="Arial, sans-serif" font-size="22" font-weight="bold" text-anchor="middle" fill="#333333">
    LangGraph Story Generation Workflow
  </text>
  <text x="500" y="55" font-family="Arial, sans-serif" font-size="12" font-style="italic" text-anchor="middle" fill="#888888">
    with Evaluation, Guardrails, Human-in-the-Loop Review &amp; Publishing
  </text>

  <!-- ═══════════════════ GENERATION PHASE ═══════════════════ -->

  <!-- story_writer node -->
  <rect x="400" y="80" width="200" height="55" rx="10" fill="#4A90E2" stroke="#000000" stroke-width="2" filter="url(#shadow)"/>
  <text x="500" y="104" font-family="Arial, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="white">story_writer</text>
  <text x="500" y="122" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">Generates story text &amp; title</text>

  <!-- image_prompter -->
  <rect x="150" y="195" width="180" height="55" rx="10" fill="#7ED321" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="240" y="218" font-family="Arial, sans-serif" font-size="12" font-weight="bold" text-anchor="middle" fill="white">image_prompter</text>
  <text x="240" y="236" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">Creates DALL-E prompts</text>

  <!-- video_prompter -->
  <rect x="670" y="195" width="180" height="55" rx="10" fill="#7ED321" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="760" y="218" font-family="Arial, sans-serif" font-size="12" font-weight="bold" text-anchor="middle" fill="white">video_prompter</text>
  <text x="760" y="236" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">Creates Sora prompts</text>

  <text x="500" y="185" font-family="Arial, sans-serif" font-size="11" font-style="italic" text-anchor="middle" fill="#666666">Parallel Execution</text>

  <!-- Fan-out routing -->
  <rect x="380" y="310" width="240" height="50" rx="10" fill="#F5A623" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="500" y="332" font-family="Arial, sans-serif" font-size="12" font-weight="bold" text-anchor="middle" fill="white">route_to_generators</text>
  <text x="500" y="350" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">Fan-out: one Send per prompt</text>

  <!-- generate_single_image -->
  <rect x="80" y="420" width="200" height="70" rx="10" fill="#BD10E0" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="180" y="448" font-family="Arial, sans-serif" font-size="12" font-weight="bold" text-anchor="middle" fill="white">generate_single_image</text>
  <text x="180" y="466" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">(×N parallel) DALL-E 3</text>

  <!-- generate_single_video -->
  <rect x="720" y="420" width="200" height="70" rx="10" fill="#BD10E0" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="820" y="448" font-family="Arial, sans-serif" font-size="12" font-weight="bold" text-anchor="middle" fill="white">generate_single_video</text>
  <text x="820" y="466" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">(×M parallel) Sora</text>

  <text x="500" y="415" font-family="Arial, sans-serif" font-size="11" font-style="italic" text-anchor="middle" fill="#666666">Dynamic Fan-out</text>

  <!-- assembler -->
  <rect x="380" y="550" width="240" height="55" rx="10" fill="#50E3C2" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="500" y="573" font-family="Arial, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="white">assembler</text>
  <text x="500" y="591" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">Validates &amp; sorts results</text>

  <text x="500" y="540" font-family="Arial, sans-serif" font-size="11" font-style="italic" text-anchor="middle" fill="#666666">Fan-in (wait for all)</text>

  <!-- ═══════════════════ EVALUATION &amp; GUARDRAIL PHASE ═══════════════════ -->

  <!-- Phase label -->
  <rect x="20" y="640" width="960" height="2" fill="#CCCCCC"/>
  <text x="500" y="665" font-family="Arial, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#555">⬇ Evaluation &amp; Guardrails (Parallel Fan-out)</text>

  <!-- story_evaluator -->
  <rect x="30" y="690" width="170" height="60" rx="10" fill="#FFD700" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="115" y="715" font-family="Arial, sans-serif" font-size="11" font-weight="bold" text-anchor="middle" fill="#333">story_evaluator</text>
  <text x="115" y="735" font-family="Arial, sans-serif" font-size="9" text-anchor="middle" fill="#333">Quality scoring (LLM)</text>

  <!-- story_guardrail -->
  <rect x="230" y="690" width="170" height="60" rx="10" fill="#FF6B6B" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="315" y="715" font-family="Arial, sans-serif" font-size="11" font-weight="bold" text-anchor="middle" fill="white">story_guardrail</text>
  <text x="315" y="735" font-family="Arial, sans-serif" font-size="9" text-anchor="middle" fill="white">Text safety (PII, etc.)</text>

  <!-- image_guardrail -->
  <rect x="430" y="690" width="170" height="60" rx="10" fill="#FF6B6B" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="515" y="715" font-family="Arial, sans-serif" font-size="11" font-weight="bold" text-anchor="middle" fill="white">image_guardrail</text>
  <text x="515" y="735" font-family="Arial, sans-serif" font-size="9" text-anchor="middle" fill="white">(×N) Vision + retry</text>

  <!-- video_guardrail -->
  <rect x="630" y="690" width="170" height="60" rx="10" fill="#FF6B6B" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="715" y="715" font-family="Arial, sans-serif" font-size="11" font-weight="bold" text-anchor="middle" fill="white">video_guardrail</text>
  <text x="715" y="735" font-family="Arial, sans-serif" font-size="9" text-anchor="middle" fill="white">(×M) Prompt mod + retry</text>

  <!-- guardrail_aggregator -->
  <rect x="350" y="820" width="300" height="55" rx="10" fill="#F5A623" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="500" y="843" font-family="Arial, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="white">guardrail_aggregator</text>
  <text x="500" y="861" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">Consolidate results, pass/fail</text>

  <text x="500" y="810" font-family="Arial, sans-serif" font-size="11" font-style="italic" text-anchor="middle" fill="#666666">Fan-in</text>

  <!-- ═══════════════════ REVIEW &amp; PUBLISH PHASE ═══════════════════ -->

  <!-- Phase label -->
  <rect x="20" y="910" width="960" height="2" fill="#CCCCCC"/>
  <text x="500" y="935" font-family="Arial, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#555">⬇ Review &amp; Publish</text>

  <!-- Conditional: hard fail? -->
  <polygon points="500,960 600,1010 500,1060 400,1010" fill="#FFFFCC" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="500" y="1005" font-family="Arial, sans-serif" font-size="10" font-weight="bold" text-anchor="middle" fill="#333">Hard fail?</text>
  <text x="500" y="1020" font-family="Arial, sans-serif" font-size="9" text-anchor="middle" fill="#333">(auto-reject config)</text>

  <!-- mark_auto_rejected -->
  <rect x="660" y="985" width="180" height="50" rx="10" fill="#D0021B" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="750" y="1010" font-family="Arial, sans-serif" font-size="11" font-weight="bold" text-anchor="middle" fill="white">mark_auto_rejected</text>
  <text x="750" y="1025" font-family="Arial, sans-serif" font-size="9" text-anchor="middle" fill="white">Auto-reject → END</text>

  <!-- human_review_gate -->
  <rect x="360" y="1100" width="280" height="55" rx="10" fill="#9013FE" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="500" y="1123" font-family="Arial, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="white">human_review_gate</text>
  <text x="500" y="1141" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">interrupt() — Graph pauses here</text>

  <!-- Conditional: decision -->
  <polygon points="500,1190 600,1240 500,1290 400,1240" fill="#FFFFCC" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="500" y="1238" font-family="Arial, sans-serif" font-size="11" font-weight="bold" text-anchor="middle" fill="#333">Decision?</text>

  <!-- publisher -->
  <rect x="230" y="1340" width="200" height="55" rx="10" fill="#417505" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="330" y="1363" font-family="Arial, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="white">publisher</text>
  <text x="330" y="1381" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">Upload to S3 production</text>

  <!-- mark_rejected -->
  <rect x="570" y="1340" width="200" height="55" rx="10" fill="#D0021B" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="670" y="1363" font-family="Arial, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="white">mark_rejected</text>
  <text x="670" y="1381" font-family="Arial, sans-serif" font-size="10" text-anchor="middle" fill="white">Human rejected → END</text>

  <!-- END nodes -->
  <circle cx="330" cy="1470" r="25" fill="#D0021B" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="330" y="1477" font-family="Arial, sans-serif" font-size="12" font-weight="bold" text-anchor="middle" fill="white">END</text>

  <circle cx="670" cy="1470" r="25" fill="#D0021B" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="670" y="1477" font-family="Arial, sans-serif" font-size="12" font-weight="bold" text-anchor="middle" fill="white">END</text>

  <circle cx="750" cy="1100" r="25" fill="#D0021B" stroke="#000" stroke-width="2" filter="url(#shadow)"/>
  <text x="750" y="1107" font-family="Arial, sans-serif" font-size="12" font-weight="bold" text-anchor="middle" fill="white">END</text>

  <!-- ═══════════════════ EDGES ═══════════════════ -->

  <!-- Generation phase -->
  <line x1="450" y1="135" x2="280" y2="195" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="365" y="162" font-family="Arial, sans-serif" font-size="9" fill="#666">parallel</text>

  <line x1="550" y1="135" x2="720" y2="195" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="635" y="162" font-family="Arial, sans-serif" font-size="9" fill="#666">parallel</text>

  <line x1="240" y1="250" x2="430" y2="310" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="760" y1="250" x2="570" y2="310" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <line x1="430" y1="360" x2="210" y2="420" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="570" y1="360" x2="790" y2="420" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <line x1="180" y1="490" x2="440" y2="550" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="820" y1="490" x2="560" y2="550" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- Assembler to guardrails fan-out -->
  <line x1="420" y1="605" x2="115" y2="690" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="450" y1="605" x2="315" y2="690" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="550" y1="605" x2="515" y2="690" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="580" y1="605" x2="715" y2="690" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- Guardrails to aggregator fan-in -->
  <line x1="115" y1="750" x2="400" y2="820" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="315" y1="750" x2="430" y2="820" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="515" y1="750" x2="500" y2="820" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <line x1="715" y1="750" x2="580" y2="820" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- Aggregator to diamond -->
  <line x1="500" y1="875" x2="500" y2="960" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- Diamond yes (hard fail) → auto_rejected -->
  <line x1="600" y1="1010" x2="660" y2="1010" stroke="#D0021B" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="625" y="1003" font-family="Arial, sans-serif" font-size="9" font-weight="bold" fill="#D0021B">yes</text>

  <!-- auto_rejected → END -->
  <line x1="750" y1="1035" x2="750" y2="1075" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- Diamond no → human_review_gate -->
  <line x1="500" y1="1060" x2="500" y2="1100" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="510" y="1085" font-family="Arial, sans-serif" font-size="9" font-weight="bold" fill="#417505">no</text>

  <!-- human_review_gate → decision diamond -->
  <line x1="500" y1="1155" x2="500" y2="1190" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- Decision → publisher (approved) -->
  <line x1="400" y1="1240" x2="330" y2="1340" stroke="#417505" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="340" y="1300" font-family="Arial, sans-serif" font-size="10" font-weight="bold" fill="#417505">approved</text>

  <!-- Decision → mark_rejected (rejected) -->
  <line x1="600" y1="1240" x2="670" y2="1340" stroke="#D0021B" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="650" y="1300" font-family="Arial, sans-serif" font-size="10" font-weight="bold" fill="#D0021B">rejected</text>

  <!-- publisher → END -->
  <line x1="330" y1="1395" x2="330" y2="1445" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- mark_rejected → END -->
  <line x1="670" y1="1395" x2="670" y2="1445" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>

  <!-- ═══════════════════ LEGEND ═══════════════════ -->

  <rect x="50" y="1540" width="900" height="230" rx="10" fill="#F9F9F9" stroke="#CCC" stroke-width="1"/>
  <text x="500" y="1565" font-family="Arial, sans-serif" font-size="14" font-weight="bold" text-anchor="middle" fill="#333">Legend</text>

  <rect x="80" y="1585" width="30" height="20" rx="5" fill="#4A90E2" stroke="#000" stroke-width="1"/>
  <text x="120" y="1599" font-family="Arial, sans-serif" font-size="11" fill="#333">Story Generation</text>

  <rect x="280" y="1585" width="30" height="20" rx="5" fill="#7ED321" stroke="#000" stroke-width="1"/>
  <text x="320" y="1599" font-family="Arial, sans-serif" font-size="11" fill="#333">Prompt Generation</text>

  <rect x="500" y="1585" width="30" height="20" rx="5" fill="#F5A623" stroke="#000" stroke-width="1"/>
  <text x="540" y="1599" font-family="Arial, sans-serif" font-size="11" fill="#333">Routing / Aggregation</text>

  <rect x="710" y="1585" width="30" height="20" rx="5" fill="#BD10E0" stroke="#000" stroke-width="1"/>
  <text x="750" y="1599" font-family="Arial, sans-serif" font-size="11" fill="#333">Media Gen (parallel)</text>

  <rect x="80" y="1620" width="30" height="20" rx="5" fill="#50E3C2" stroke="#000" stroke-width="1"/>
  <text x="120" y="1634" font-family="Arial, sans-serif" font-size="11" fill="#333">Assembly</text>

  <rect x="280" y="1620" width="30" height="20" rx="5" fill="#FFD700" stroke="#000" stroke-width="1"/>
  <text x="320" y="1634" font-family="Arial, sans-serif" font-size="11" fill="#333">Evaluation (LLM)</text>

  <rect x="500" y="1620" width="30" height="20" rx="5" fill="#FF6B6B" stroke="#000" stroke-width="1"/>
  <text x="540" y="1634" font-family="Arial, sans-serif" font-size="11" fill="#333">Guardrails (with retry)</text>

  <rect x="710" y="1620" width="30" height="20" rx="5" fill="#9013FE" stroke="#000" stroke-width="1"/>
  <text x="750" y="1634" font-family="Arial, sans-serif" font-size="11" fill="#333">Human Review (interrupt)</text>

  <rect x="80" y="1655" width="30" height="20" rx="5" fill="#417505" stroke="#000" stroke-width="1"/>
  <text x="120" y="1669" font-family="Arial, sans-serif" font-size="11" fill="#333">Publisher (S3)</text>

  <rect x="280" y="1655" width="30" height="20" rx="5" fill="#D0021B" stroke="#000" stroke-width="1"/>
  <text x="320" y="1669" font-family="Arial, sans-serif" font-size="11" fill="#333">Rejection / End</text>

  <polygon points="515,1653 530,1665 515,1677 500,1665" fill="#FFFFCC" stroke="#000" stroke-width="1"/>
  <text x="545" y="1669" font-family="Arial, sans-serif" font-size="11" fill="#333">Conditional Branch</text>

  <!-- Notes -->
  <text x="500" y="1720" font-family="Arial, sans-serif" font-size="10" font-style="italic" text-anchor="middle" fill="#666">
    All fan-out stages use LangGraph Send for true parallelism. Media guardrails include internal retry loops.
  </text>
  <text x="500" y="1738" font-family="Arial, sans-serif" font-size="10" font-style="italic" text-anchor="middle" fill="#666">
    human_review_gate uses interrupt() — graph state is checkpointed to PostgreSQL and resumes via API.
  </text>
  <text x="500" y="1756" font-family="Arial, sans-serif" font-size="10" font-style="italic" text-anchor="middle" fill="#666">
    Celery Beat runs hourly timeout checks to auto-reject stale reviews.
  </text>
</svg>'''

    # Create docs directory if it doesn't exist
    os.makedirs('docs', exist_ok=True)

    # Write SVG file
    output_path = 'docs/graph_structure.svg'
    with open(output_path, 'w') as f:
        f.write(svg_content)

    print(f"Graph diagram saved to: {output_path}")
    print("Note: SVG format is scalable and can be converted to PNG if needed")

    # Also try to create a PNG if PIL is available
    try:
        from PIL import Image
        import cairosvg
        png_path = 'docs/graph_structure.png'
        cairosvg.svg2png(bytestring=svg_content.encode('utf-8'), write_to=png_path)
        print(f"PNG version also saved to: {png_path}")
    except ImportError:
        print("To generate PNG, install: pip install cairosvg pillow")
        print("Or use an online SVG to PNG converter")

    return output_path


if __name__ == '__main__':
    create_graph_diagram()
