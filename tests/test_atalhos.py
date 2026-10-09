import unittest

from capturador import atalhos


class InterpretarAtalho(unittest.TestCase):
    def test_combinacao_comum(self):
        mods, vk = atalhos.interpretar("ctrl+shift+f9")
        self.assertEqual(mods, atalhos.MOD_CONTROL | atalhos.MOD_SHIFT)
        self.assertEqual(vk, 0x78)  # VK_F9

    def test_letra_e_digito(self):
        self.assertEqual(atalhos.interpretar("ctrl+alt+s")[1], ord("S"))
        self.assertEqual(atalhos.interpretar("ctrl+1")[1], ord("1"))

    def test_print_sem_modificador_e_valido(self):
        self.assertEqual(atalhos.interpretar("print"), (0, 0x2C))

    def test_f_sozinha_e_valida_mas_letra_sozinha_nao(self):
        atalhos.interpretar("f9")
        with self.assertRaises(ValueError):
            atalhos.interpretar("s")

    def test_invalidos(self):
        for texto in ("", "ctrl+", "ctrl+shift+ç", "meta+s", "ctrl+f25"):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                atalhos.interpretar(texto)

    def test_formatar(self):
        self.assertEqual(atalhos.formatar("ctrl+shift+f9"), "Ctrl+Shift+F9")
        self.assertEqual(atalhos.formatar("ctrl+alt+s"), "Ctrl+Alt+S")


class AtalhoDoEvento(unittest.TestCase):
    CTRL, SHIFT, ALT = 0x4, 0x1, 0x20000

    def test_ctrl_shift_f9(self):
        self.assertEqual(atalhos.atalho_do_evento(self.CTRL | self.SHIFT, 0x78), "ctrl+shift+f9")

    def test_ordem_canonica_ctrl_alt_shift(self):
        self.assertEqual(atalhos.atalho_do_evento(self.SHIFT | self.ALT | self.CTRL, ord("S")),
                         "ctrl+alt+shift+s")

    def test_so_modificador_continua_aguardando(self):
        for vk in (16, 17, 18, 162, 160):
            self.assertIsNone(atalhos.atalho_do_evento(self.CTRL, vk))

    def test_letra_sem_modificador_e_rejeitada(self):
        with self.assertRaises(ValueError):
            atalhos.atalho_do_evento(0, ord("A"))

    def test_tecla_desconhecida_e_rejeitada(self):
        with self.assertRaises(ValueError):
            atalhos.atalho_do_evento(self.CTRL, 0xBA)  # ';' / 'ç'

    def test_resultado_e_aceito_por_interpretar(self):
        texto = atalhos.atalho_do_evento(self.CTRL | self.ALT, 0x77)
        atalhos.interpretar(texto)


if __name__ == "__main__":
    unittest.main()
