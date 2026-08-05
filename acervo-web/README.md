# acervo-web

Dashboard sobre `acervo-api`. Next.js + TypeScript.

## Por que Next y no una SPA

Los server components consultan el API sin exponerlo al navegador, asi que
`acervo-api` puede quedarse dentro de la red del compose y no publicar puerto.

## Alcance

Lectura. El dashboard no dispara pipelines: para eso esta la UI de Dagster, que
ya existe y hace ese trabajo mejor.

## Estado

Esqueleto. Sin `create-next-app` todavia: no hay API que consultar, y
scaffoldear un front sin datos produce mocks que despues hay que borrar.

## Siguiente

Esperar. Este es el ultimo servicio en orden de necesidad — primero tiene que
haber una tabla gold, luego un endpoint que la sirva.
