# SOCKS5 Proxy Finder

Herramienta en Python para localizar un proxy SOCKS5 candidato por país,
aplicar unos filtros básicos de anonimato y disponibilidad, comprobar
que el puerto acepta conexiones TCP y guardar los resultados en varios
formatos.

> **Aviso:** los proxies de listas públicas son servicios de terceros.
> No los utilices para transmitir contraseñas, datos personales ni
> información sensible. La comprobación TCP de este script no garantiza
> que el proxy funcione correctamente como SOCKS5, que oculte la IP de
> origen en todos los escenarios ni que el servidor sea de confianza.

## Fuente de datos

El listado se obtiene del repositorio
**[proxyscrape/free-proxy-list](https://github.com/proxyscrape/free-proxy-list)**,
en concreto de sus archivos JSON organizados por país y protocolo. El
script consulta la distribución servida mediante jsDelivr:

``` text
https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/
proxies/countries/{country}/{protocol}/data.json
```

El proyecto indica en el comentario del código que el repositorio se
actualiza aproximadamente cada cinco minutos. La disponibilidad y los
datos concretos pueden cambiar entre ejecuciones.

## Requisitos

-   Python 3.8 o posterior.
-   Conexión a Internet.
-   Acceso de red a los servidores de la lista y a los puertos de los
    proxies candidatos.

El script utiliza únicamente módulos incluidos en la biblioteca estándar
de Python; no requiere instalar paquetes adicionales.

## Configuración

Los parámetros principales se encuentran al principio del archivo:

  --------------------------------------------------------------------------
  Parámetro                              Valor inicial Descripción
  ----------------------- ---------------------------- ---------------------
  `COUNTRIES`                         `us`, `ru`, `cn` Países en los que
                                                       buscar proxies.

  `PROTOCOL`                                  `socks5` Protocolo consultado
                                                       en el repositorio.

  `MIN_ANONYMITY_LEVEL`                            `1` Exige nivel
                                                       `anonymous` o
                                                       `elite`.

  `MINIMUM_UPTIME`                                `50` Uptime mínimo,
                                                       expresado en
                                                       porcentaje.

  `TIMEOUT`                                        `4` Tiempo máximo, en
                                                       segundos, para la
                                                       conexión TCP de
                                                       comprobación.
  --------------------------------------------------------------------------

La prioridad de anonimato está definida como `elite` \> `anonymous` \>
`transparent`. Con la configuración inicial se descartan los proxies
transparentes.

Para cambiar los países, modifica el diccionario `COUNTRIES`. Utiliza
códigos de país compatibles con la estructura de directorios del
repositorio.

## Ejecución

Guarda el código, por ejemplo, como `proxy_finder.py`. Desde una
terminal, ejecuta:

``` bash
python3 proxy_finder.py
```

En Windows también puedes utilizar:

``` powershell
py proxy_finder.py
```

El programa descarga la lista de cada país, filtra los candidatos por
anonimato y uptime, los ordena dando prioridad al anonimato, al uptime y
a la latencia publicada, y prueba sus puertos mediante una conexión TCP.

Por cada país selecciona el primer candidato que supera esa
comprobación. Si no encuentra uno válido, muestra el país como no
disponible.

## Archivos generados

Si se encuentra al menos un proxy, el script crea estos archivos en el
directorio desde el que se ejecuta:

  -----------------------------------------------------------------------
  Archivo                             Contenido
  ----------------------------------- -----------------------------------
  `selected_proxies.txt`              Resumen legible con país, IP,
                                      puerto, protocolo, anonimato,
                                      uptime, latencias y metadatos
                                      disponibles.

  `proxies.txt`                       Lista de proxies en formato
                                      `socks5 IP PUERTO`, compatible con
                                      la sintaxis habitual de
                                      Proxychains.

  `proxychains_config.txt`            Fragmento de configuración con
                                      `strict_chain`, `proxy_dns` y la
                                      lista de proxies encontrados.

  `selected_proxies.json`             Metadatos completos de los proxies
                                      seleccionados en formato JSON.
  -----------------------------------------------------------------------

Los archivos contienen únicamente los países para los que se haya
encontrado un candidato. Si no se encuentra ninguno, no se generan.

## Uso con Proxychains

1.  Ejecuta el script.
2.  Revisa `proxychains_config.txt`.
3.  Haz una copia de seguridad de tu configuración actual de
    Proxychains.
4.  Integra el fragmento generado en el archivo de configuración
    correspondiente a tu instalación.
5.  Comprueba que la configuración resultante es válida antes de
    utilizarla.

El fragmento utiliza `strict_chain`: Proxychains intentará encadenar los
proxies listados en el orden indicado. Por tanto, que el archivo
contenga varios países no significa que se haya verificado una ruta
completa entre ellos.

## Qué comprueba --- y qué no

**Sí comprueba:**

-   Que el candidato aparece en el listado descargado.
-   Que su nivel de anonimato y uptime publicados cumplen los umbrales
    configurados.
-   Que se puede abrir una conexión TCP al par IP/puerto dentro del
    timeout establecido.

**No comprueba:**

-   El protocolo SOCKS5 mediante una negociación real.
-   Que el proxy permita completar una petición HTTP o HTTPS.
-   La IP pública de salida ni la ubicación efectiva de esa salida.
-   Que el nivel de anonimato publicado sea correcto o siga siéndolo.
-   Que el proxy permanezca disponible después de la prueba.

La latencia TCP medida por el script es una medición puntual de conexión
al puerto; no equivale necesariamente a la latencia de navegación a
través del proxy. Los valores de uptime y latencia descargados dependen
de la información publicada por la fuente.

## Resolución de problemas

-   **No hay proxies para un país:** puede que el repositorio no
    publique candidatos para ese país y protocolo en ese momento.
-   **Error HTTP 404:** no se ha encontrado el archivo solicitado para
    esa combinación de país y protocolo.
-   **Error de descarga:** comprueba la conexión a Internet y vuelve a
    intentarlo más tarde.
-   **No se supera la prueba TCP:** el proxy puede estar caído, filtrado
    por la red o no aceptar conexiones desde tu ubicación.
-   **No se generan archivos:** el script solo guarda resultados cuando
    encuentra al menos un candidato válido.

------------------------------------------------------------------------

**La selección es orientativa y no constituye una
auditoría de seguridad ni una garantía de anonimato. Verifica los
proxies de forma independiente y utiliza únicamente servicios cuyo uso
esté permitido.**
