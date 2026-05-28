def gerar_html_agenda(d: dict) -> str:
    C_CANT  = "#1a78b4"
    C_TES   = "#1a3566"
    C_TES_I = "#1a5fa8"
    C_MIN   = "#8a6200"
    C_MIN_I = "#a07800"
    C_NVC   = "#cc0000"
    C_NVC_I = "#1a5fa8"

    def row(num, titulo, duracao, bg, cor_item):
        if not str(titulo).strip():
            return ""
        dur = (
            f'<br><span style="font-size:12px;color:#888;margin-left:4px;">({duracao})</span>'
            if str(duracao).strip()
            else ""
        )
        return (
            f'<div style="padding:6px 14px;background:{bg};border-bottom:1px solid #e8e8e8;">'
            f'<span style="color:{cor_item};font-weight:bold;">{num}. {titulo}</span>{dur}'
            f"</div>"
        )

    def sec_header(texto, bg):
        return (
            f'<div style="background:{bg};color:white;padding:9px 14px;'
            f"font-weight:bold;font-size:14.5px;letter-spacing:0.3px;\">"
            f"{texto}</div>"
        )

    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;'
        "border:1px solid #ccc;border-radius:10px;overflow:hidden;"
        'box-shadow:0 2px 8px rgba(0,0,0,0.12);margin:auto;">'
    )

    html += '<div style="padding:12px 14px 8px;background:#ffffff;">'
    html += f'<div style="font-size:19px;font-weight:bold;color:#111;">{d.get("data_texto", "")}</div>'
    if d.get("escritura"):
        html += f'<div style="color:{C_CANT};font-size:13px;font-weight:bold;margin-top:2px;">{d["escritura"]}</div>'
    html += "</div>"
    html += '<hr style="margin:0;border:0;border-top:1px solid #ddd;">'

    if d.get("cantico_abertura"):
        html += (
            f'<div style="padding:7px 14px;font-size:13px;background:#fff;">'
            f'<span style="color:{C_CANT};font-weight:bold;">Cântico {d["cantico_abertura"]}</span>'
            f" e oração | <strong>Comentários iniciais</strong> (1 min)</div>"
        )

    html += '<div style="margin-top:8px;">'
    html += sec_header("TESOUROS DA PALAVRA DE DEUS", C_TES)
    for it in d.get("tesouros", []):
        html += row(it["num"], it["titulo"], it.get("duracao", ""), "#f0f4ff", C_TES_I)
    html += "</div>"

    html += '<div style="margin-top:8px;">'
    html += sec_header("FAÇA SEU MELHOR NO MINISTÉRIO", C_MIN)
    for it in d.get("ministerio", []):
        html += row(it["num"], it["titulo"], it.get("duracao", ""), "#fffcf0", C_MIN_I)
    html += "</div>"

    html += '<div style="margin-top:8px;">'
    html += sec_header("NOSSA VIDA CRISTÃ", C_NVC)
    if d.get("cantico_meio"):
        html += (
            f'<div style="padding:6px 14px;background:#fff5f5;border-bottom:1px solid #e8e8e8;">'
            f'<span style="color:{C_CANT};font-weight:bold;">Cântico {d["cantico_meio"]}</span></div>'
        )
    for it in d.get("vida_crista", []):
        html += row(it["num"], it["titulo"], it.get("duracao", ""), "#fff5f5", C_NVC_I)
    html += "</div>"

    if d.get("cantico_final"):
        html += (
            f'<hr style="margin:0;border:0;border-top:1px solid #ddd;">'
            f'<div style="padding:9px 14px;font-size:13px;background:#fff;">'
            f"<strong>Comentários finais</strong> (3 min) | "
            f'<span style="color:{C_CANT};font-weight:bold;">Cântico {d["cantico_final"]}</span>'
            f" e oração</div>"
        )

    html += "</div>"
    return html
