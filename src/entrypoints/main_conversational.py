#!/usr/bin/env python3
"""
Zenic-Agents — Modo Conversacional Local.

Asistente conversacional interactivo SIN servidor HTTP.
Usa el motor conversacional interno directamente desde CLI.

Uso:
  python3 main_conversational.py                    # Modo interactivo
  python3 main_conversational.py --debug            # Modo debug
"""

import os
import sys
import logging
import argparse

from src.core.env_loader import load_env
load_env()

from src.core.shared._version import ZENIC_VERSION_STR, ZENIC_FULL_NAME

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ZENIC.CONVERSATIONAL")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"ZENIC-AGENTS {ZENIC_VERSION_STR} - Conversational Assistant (Local)"
    )
    parser.add_argument('--debug', action='store_true', help='Modo debug')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize conversational engine
    engine = None
    try:
        from src.core.conversational import ConversationEngine
        engine = ConversationEngine()
        logger.info("ConversationEngine initialized")
    except Exception as e:
        logger.warning(f"ConversationEngine unavailable: {e}")
        logger.info("Falling back to core orchestrator")

    # Fallback to core orchestrator
    if engine is None:
        try:
            from src.core.orchestrator import ZenicOrchestrator
            engine = ZenicOrchestrator()
            logger.info("Using ZenicOrchestrator as fallback")
        except Exception as e:
            print(f"ERROR: No engine available: {e}")
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  ZENIC-AGENTS {ZENIC_VERSION_STR} — Asistente Conversacional")
    print(f"  Motor: {type(engine).__name__}")
    print(f"  Modo: Local (sin servidor HTTP)")
    print(f"{'=' * 60}")
    print(f"  Escribe tu consulta. 'quit' para salir.")
    print(f"{'=' * 60}\n")

    # Interactive loop
    import asyncio
    while True:
        try:
            user_input = input("zenic-chat> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break

        try:
            loop = asyncio.new_event_loop()
            if hasattr(engine, 'execute'):
                result = loop.run_until_complete(engine.execute(user_input))
            elif hasattr(engine, 'process'):
                result = loop.run_until_complete(engine.process(user_input))
            else:
                result = {"error": "Engine has no execute/process method"}
            loop.close()

            if isinstance(result, dict):
                if result.get('error'):
                    print(f"  ❌ {result['error']}")
                elif result.get('response'):
                    print(f"  {result['response']}")
                elif result.get('code'):
                    print(f"  Code:\n{result['code']}")
                elif result.get('explanations'):
                    for exp in result['explanations']:
                        print(f"  {exp}")
                else:
                    print(f"  {result}")
            else:
                print(f"  {result}")
        except Exception as e:
            print(f"  Error: {e}")

    print("\n  Hasta luego!")
    sys.exit(0)


if __name__ == "__main__":
    main()
