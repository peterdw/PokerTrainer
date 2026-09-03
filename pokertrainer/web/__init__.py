"""Browserversie van de Poker Trainer.

Dezelfde spelmotor als de console, maar de mens speelt in een webpagina.
Alleen de standaardbibliotheek wordt gebruikt (``http.server``).

- adapters   : WebIO en WebHumanStrategy (Adapter), PacedStrategy (Decorator)
- presenter  : TablePresenter (Observer) vertaalt gebeurtenissen naar JSON
- session    : WebSession: één spelsessie in een achtergrondthread
- content    : statische lesinhoud en quizvragen als JSON
- server     : HTTP-server met Server-Sent Events voor het spelverloop
"""
