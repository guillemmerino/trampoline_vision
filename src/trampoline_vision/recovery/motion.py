"""Espai reservat per estimar continuïtat de moviment entre fragments.

Consumirà observacions amb timestamps reals i produirà estimacions amb
incertesa per comparar finals i inicis. Temps i distàncies tindran unitats
explícites; la incertesa podrà augmentar amb la durada de desaparició.

El model de moviment i els límits es decidiran amb experiments. No s'imposa
una paràbola ni es considera el centre de la caixa com a centre de massa.
Una estimació geomètrica no es publicarà com a detecció observada.
"""
