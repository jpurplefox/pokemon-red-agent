# Notas de experimentación

## Qwen 3.5 9B
- Casi siempre elige Charmander como inicial, lo que complica su batalla contra Brock
  (Charmander es tipo Fuego vs los tipo Roca de Brock).

## Navegación / Diseño del mapa
- El modelado original del juego genera confusión en los LLMs: el Bosque Verde tiene
  "Ruta 2 Abajo" y "Ruta 2 Arriba" como salidas distintas. El modelo las percibe como
  el mismo lugar ("Ruta 2") pero tiene que elegir entre dos opciones que semánticamente
  le parecen idénticas. Esto es un artefacto de cómo los desarrolladores particionaron
  el mapa en zonas, no una distinción que tenga sentido narrativo para el agente.
