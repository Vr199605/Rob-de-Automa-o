#!/usr/bin/env python3
"""
Robô de automação de texto
--------------------------
Duas tarefas:
  escrever  -> escreve qualquer tipo de texto (e-mail, artigo, poema, carta, post...)
  corrigir  -> corrige texto conforme o Acordo Ortográfico da Língua Portuguesa (1990)

Requisitos:  pip install anthropic
Chave:       defina a variável de ambiente ANTHROPIC_API_KEY
"""

import argparse
import difflib
import os
import sys
import time

try:
    import anthropic
except ImportError:
    sys.exit("Falta a biblioteca 'anthropic'. Instale com: pip install anthropic")

MODELO = os.environ.get("ROBO_MODELO", "claude-sonnet-5-5")
TAMANHO_BLOCO = 6000  # caracteres por bloco na correção de textos longos

PROMPT_ESCREVER = """Você é um redator profissional em português do Brasil.
Escreva exatamente o tipo de texto pedido, com o tom e o tamanho solicitados.
Use a ortografia atual (Acordo Ortográfico de 1990), gramática correta e pontuação adequada.
Entregue apenas o texto final, sem comentários, explicações ou introduções."""

PROMPT_CORRIGIR = """Você é um revisor de textos em português, especialista no Acordo Ortográfico da Língua Portuguesa de 1990 (a "nova ortografia").

Corrija o texto recebido quanto a: ortografia, acentuação, hífen, uso de maiúsculas e minúsculas, pontuação, concordância, regência, crase e digitação.

Regras do Acordo que você deve aplicar:
- Sem trema em palavras portuguesas (frequência, linguiça, cinquenta); mantém-se em nomes próprios estrangeiros.
- Sem acento em ditongos abertos "ei" e "oi" de paroxítonas (ideia, heroico, assembleia, jiboia).
- Sem acento em "i" e "u" tônicos depois de ditongo em paroxítonas (feiura, baiuca).
- Sem acento em "êem" e "ôo" (veem, leem, creem, voo, enjoo, perdoo).
- Sem acento diferencial em pára, pêlo, pólo, pêra, péla etc. Mantêm-se: pôr (verbo), pôde (passado), e o par por/pôr, têm/tem, vêm/vem.
- Sem acento agudo no "u" tônico de gue/gui, que/qui (averigue, argui).
- Hífen: segundo as regras do Acordo (ex.: anti-inflamatório, autoescola, microondas -> micro-ondas, extraordinário, contrarregra, super-homem).
- Alfabeto de 26 letras (k, w, y incluídos); minúsculas em meses, dias da semana e pontos cardeais (quando não forem nome de região).

Regras de conduta:
- Preserve o sentido, o estilo, a voz e a estrutura do autor. Não reescreva, não resuma, não acrescente conteúdo.
- Preserve parágrafos, quebras de linha, listas, URLs, e-mails, números, códigos e nomes próprios.
- Não altere citações literais de textos antigos nem palavras em outros idiomas.
- Se houver dúvida real entre duas formas corretas, mantenha a do autor.
- Entregue SOMENTE o texto corrigido, sem comentários, sem aspas ao redor e sem explicações."""


def cliente():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Defina a variável de ambiente ANTHROPIC_API_KEY antes de usar o robô.")
    return anthropic.Anthropic()


def chamar(api, sistema, usuario, max_tokens=4096, temperatura=0.7, tentativas=3):
    """Chama o modelo com repetição automática em caso de falha temporária."""
    for n in range(1, tentativas + 1):
        try:
            resp = api.messages.create(
                model=MODELO,
                max_tokens=max_tokens,
                temperature=temperatura,
                system=sistema,
                messages=[{"role": "user", "content": usuario}],
            )
            texto = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not texto:
                raise ValueError("resposta vazia do modelo")
            return texto
        except (anthropic.APIConnectionError, anthropic.RateLimitError,
                anthropic.InternalServerError, ValueError) as erro:
            if n == tentativas:
                sys.exit(f"Falha após {tentativas} tentativas: {erro}")
            time.sleep(2 * n)
        except anthropic.AuthenticationError:
            sys.exit("Chave de API inválida.")
        except anthropic.APIStatusError as erro:
            sys.exit(f"Erro da API: {erro}")


def dividir_em_blocos(texto, limite=TAMANHO_BLOCO):
    """Divide o texto em blocos respeitando parágrafos, sem perder nada."""
    paragrafos = texto.split("\n\n")
    blocos, atual = [], ""
    for p in paragrafos:
        # parágrafo único maior que o limite: corta por linhas/frases
        while len(p) > limite:
            corte = max(p.rfind("\n", 0, limite), p.rfind(". ", 0, limite) + 1, 0) or limite
            if atual:
                blocos.append(atual)
                atual = ""
            blocos.append(p[:corte])
            p = p[corte:].lstrip(" ") if p[corte:corte + 1] == " " else p[corte:]
        candidato = f"{atual}\n\n{p}" if atual else p
        if len(candidato) > limite and atual:
            blocos.append(atual)
            atual = p
        else:
            atual = candidato
    if atual:
        blocos.append(atual)
    return blocos


def corrigir_texto(api, texto):
    blocos = dividir_em_blocos(texto)
    saida = []
    for i, bloco in enumerate(blocos, 1):
        if len(blocos) > 1:
            print(f"Corrigindo bloco {i}/{len(blocos)}...", file=sys.stderr)
        if not bloco.strip():
            saida.append(bloco)
            continue
        corrigido = chamar(api, PROMPT_CORRIGIR, bloco, temperatura=0.0)
        # Verificação de segurança: a correção não pode mudar muito o tamanho
        razao = len(corrigido) / max(len(bloco), 1)
        if razao < 0.7 or razao > 1.3:
            print(f"Aviso: o bloco {i} mudou muito de tamanho; mantive o original "
                  "para evitar perda de conteúdo.", file=sys.stderr)
            corrigido = bloco
        saida.append(corrigido)
    return "\n\n".join(saida)


def mostrar_diferencas(antes, depois):
    for linha in difflib.unified_diff(
        antes.splitlines(), depois.splitlines(),
        fromfile="original", tofile="corrigido", lineterm="", n=0,
    ):
        print(linha, file=sys.stderr)


def ler_entrada(args):
    if args.arquivo:
        try:
            with open(args.arquivo, encoding="utf-8") as f:
                return f.read()
        except OSError as erro:
            sys.exit(f"Não consegui abrir '{args.arquivo}': {erro}")
    if args.texto:
        return args.texto
    if not sys.stdin.isatty():
        return sys.stdin.read()
    sys.exit("Informe o texto com --texto, --arquivo ou por entrada padrão (pipe).")


def salvar_ou_imprimir(texto, caminho):
    if caminho:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(texto + "\n")
        print(f"Salvo em: {caminho}", file=sys.stderr)
    else:
        print(texto)


def cmd_escrever(args):
    api = cliente()
    pedido = [f"Tipo de texto: {args.tipo}", f"Assunto/instruções: {args.assunto}"]
    if args.tom:
        pedido.append(f"Tom: {args.tom}")
    if args.tamanho:
        pedido.append(f"Tamanho: {args.tamanho}")
    texto = chamar(api, PROMPT_ESCREVER, "\n".join(pedido), max_tokens=8192)
    if args.revisar:
        texto = corrigir_texto(api, texto)
    salvar_ou_imprimir(texto, args.saida)


def cmd_corrigir(args):
    api = cliente()
    original = ler_entrada(args)
    corrigido = corrigir_texto(api, original)
    if args.diff:
        mostrar_diferencas(original, corrigido)
    salvar_ou_imprimir(corrigido, args.saida)


def main():
    p = argparse.ArgumentParser(description="Robô de escrita e correção de textos em português.")
    sub = p.add_subparsers(dest="comando", required=True)

    e = sub.add_parser("escrever", help="escreve qualquer tipo de texto")
    e.add_argument("assunto", help="o que escrever (tema, contexto, instruções)")
    e.add_argument("--tipo", default="texto livre",
                   help="ex.: e-mail, artigo, poema, carta, post, discurso, resumo")
    e.add_argument("--tom", help="ex.: formal, informal, humorístico, técnico")
    e.add_argument("--tamanho", help="ex.: 3 parágrafos, 200 palavras, curto")
    e.add_argument("--revisar", action="store_true",
                   help="passa o texto pelo corretor ortográfico depois de escrever")
    e.add_argument("--saida", help="arquivo onde salvar o resultado")
    e.set_defaults(func=cmd_escrever)

    c = sub.add_parser("corrigir", help="corrige texto na nova ortografia")
    c.add_argument("--texto", help="texto a corrigir")
    c.add_argument("--arquivo", help="arquivo .txt a corrigir")
    c.add_argument("--saida", help="arquivo onde salvar o texto corrigido")
    c.add_argument("--diff", action="store_true", help="mostra o que foi alterado")
    c.set_defaults(func=cmd_corrigir)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
