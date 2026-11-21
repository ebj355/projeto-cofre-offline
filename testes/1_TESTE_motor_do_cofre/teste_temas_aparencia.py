# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Verifica as seis paletas fixas, o contraste e a persistência local da escolha."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import cofre_senhas as c


class TestTemasAparencia(unittest.TestCase):
    def test_seis_temas_e_contraste_de_textos(self):
        self.assertEqual(len(c.PALETAS), 6)
        self.assertEqual(c.TEMA_PADRAO, "Roxo (atual)")

        for nome in c.PALETAS:
            with self.subTest(tema=nome):
                paleta = c._cores_da_paleta(nome)
                self.assertGreaterEqual(c._contraste_wcag(paleta["prim_fg"], paleta["prim"]), 4.5)
                for estado in ("ok", "alerta", "perigo"):
                    self.assertGreaterEqual(
                        c._contraste_wcag(paleta[estado], paleta[f"{estado}_fundo"]), 4.5,
                        f"Contraste insuficiente para {estado} no tema {nome}",
                    )
                    self.assertGreaterEqual(
                        c._contraste_wcag(c._texto_contraste(paleta[estado]), paleta[estado]), 4.5,
                        f"Texto sobre o fundo de {estado} insuficiente no tema {nome}",
                    )
                    for superficie in ("fundo", "sup", "campo"):
                        self.assertGreaterEqual(
                            c._contraste_wcag(paleta[estado], paleta[superficie]), 4.5,
                            f"Contraste de {estado} sobre {superficie} insuficiente no tema {nome}",
                        )

    def test_preferencia_salva_somente_o_tema(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "preferencias.json")
            with mock.patch.object(c, "_caminho_preferencias", return_value=caminho):
                c._salvar_preferencia_tema("Rosa")
                with open(caminho, encoding="utf-8") as arquivo:
                    dados = json.load(arquivo)
                self.assertEqual(dados, {"tema": "Rosa"})
                self.assertEqual(c._carregar_preferencia_tema(), "Rosa")

    def test_preferencia_personalizada_antiga_migra_para_paleta_base(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "preferencias.json")
            with open(caminho, "w", encoding="utf-8") as arquivo:
                json.dump({"tema": "Personalizada", "cor": "#e04a92", "base": "Rosa"}, arquivo)
            with mock.patch.object(c, "_caminho_preferencias", return_value=caminho):
                self.assertEqual(c._carregar_preferencia_tema(), "Rosa")

    def test_preferencia_invalida_volta_ao_roxo(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "preferencias.json")
            with open(caminho, "w", encoding="utf-8") as arquivo:
                json.dump(["estado", "inválido"], arquivo)
            with mock.patch.object(c, "_caminho_preferencias", return_value=caminho):
                self.assertEqual(c._carregar_preferencia_tema(), c.TEMA_PADRAO)

    def test_monogramas_reconhecem_servicos_urls_e_categoria(self):
        casos = {
            "https://www.nubank.com.br/conta": "NU",
            "instagram.com": "IG",
            "drive.google.com": "GD",
            "amazonprimevideo.com": "PV",
            "Academia do Bairro": "",
        }
        for nome, esperado in casos.items():
            with self.subTest(servico=nome):
                self.assertEqual(c.marca_servico(nome), esperado)
        self.assertEqual(c.marca_servico("Academia do Bairro", "Bancos"), "BC")


if __name__ == "__main__":
    unittest.main()
