# Seguros Barú — Memo de diseño y política contable IFRS 17 (Fase 0)

Oct 2, 2026 · @Heydi

## 1. Propósito y alcance

Este memo fija las decisiones de diseño y las políticas contables con las que Seguros Barú, S.A. aplicará IFRS 17 en sus cierres del 31 de diciembre de 2023, 2024 y 2025. Cada decisión cita el párrafo de la norma que la respalda, de modo que el motor en Python implemente reglas ya justificadas y no criterios improvisados durante la programación.

Seguros Barú es una entidad ficticia. Antes de adoptar el nombre se verificó que no aparece en el [registro de compañías de seguros](https://www.superseguros.gob.pa/sujetos-regulados/companias-de-seguros/) ni en el de [reaseguradoras](https://superseguros.gob.pa/sancion/companias-de-reaseguros/) de la Superintendencia de Seguros y Reaseguros de Panamá (SSRP), ni en búsquedas web generales. Todos los datos serán sintéticos, generados con semilla fija y calibrados con fuentes públicas; no se usa ningún dato ni supuesto de clientes reales.

Las citas provienen del texto de IFRS 17 guardado en el proyecto, que incorpora las modificaciones de 2020 y 2021. Ese texto ya refleja los cambios de consecuencia de IFRS 18, pero IFRS 18 rige desde 2027; por eso los estados de 2023–2025 se presentan con NIC 1, y el anexo A explica cómo cambiarían con IFRS 18.

El proyecto aplica IFRS 17 tal como la emite el IASB. No adopta las disposiciones locales de la SSRP sobre NIIF 17 (Acuerdo 1 de 2024), porque no coinciden al 100% con la norma. Las leyes panameñas solo se usan para hechos que IFRS 17 no regula, como los impuestos sobre primas y el capital mínimo.

## 2. Resumen de elecciones de política contable

La tabla reúne las decisiones del memo para consultarlas de un vistazo; cada fila se desarrolla en la sección indicada. Las filas marcadas como “propuesta” esperan tu confirmación en comentarios.

| Tema | Decisión | Párrafos | Sección |
| --- | --- | --- | --- |
| Transición | No hay transición: la entidad nace el 1 de enero de 2023, fecha de vigencia de IFRS 17, sin contratos previos | C1 | 3 |
| Componentes de inversión | No se separan en vida con ahorro, porque están altamente interrelacionados con la cobertura | 11(b), B31–B32 | 5 |
| Portafolios | Cinco portafolios emitidos (uno por línea de producto) y uno de reaseguro cedido | 14, 61 | 6 |
| Cohortes | Año calendario de emisión (enero–diciembre) | 22 | 6 |
| Grupos de rentabilidad | Oneroso, sin posibilidad significativa de volverse oneroso y resto, con reglas cuantitativas por modelo | 16–19 | 6 |
| Reconocimiento | Fecha de inicio de cobertura, que coincide con el vencimiento de la primera prima | 25, 28 | 6 |
| Autos e incendio/hogar | PAA, porque cada contrato cubre un año o menos | 53(b) | 7 |
| Todo Riesgo Construcción | Decide el test de elegibilidad con umbral de 5% del LRC del GMM (confirmado) | 53(a), 54 | 7 |
| Vida temporal y vida con ahorro | GMM; vida con ahorro no cumple B101 y no va a VFA | 29, B101, B106(b) | 7 |
| Gastos de adquisición en PAA | Autos los difiere y amortiza; incendio/hogar los reconoce como gasto | 55(a)(ii), 59(a) | 7 |
| Financiación del LRC en PAA | No se ajusta, porque las primas vencen dentro del año de cobertura | 56 | 7 |
| Descuento del LIC en PAA | Autos lo descuenta; incendio/hogar no, porque paga en menos de un año | 59(b) | 7 |
| Curva de descuento | Bottom-up: TNC del Tesoro de fin de mes más el diferencial HQM − TNC completo, es decir, la curva HQM, interpolada a plazos mensuales; opción de deducir crédito | 36, B78–B80 | 8 |
| Tasas bloqueadas | Promedio ponderado por prima de las curvas mensuales del año de emisión | B72(b), B73 | 8 |
| Ajuste por riesgo | Costo de capital 6% en vida; percentil 75 en daños y construcción; se revela el nivel de confianza equivalente | 37, B86–B92, 119 | 10 |
| Desagregación del ajuste por riesgo | No se desagrega: todo su cambio va al resultado del servicio de seguros | 81 | 10 |
| Unidades de cobertura | Temporal: suma asegurada en vigor esperada; ahorro: cargo por riesgo más tarifa de inversión; sin descontar (propuesta) | B119, B119B | 12 |
| Ingresos y gastos financieros | OCI en vida temporal y su reaseguro; todo en resultados en el resto (propuesta) | 88, B129, B131 | 14 |
| Presentación del reaseguro | Importes recuperados y asignación de primas por separado; comisión de cesión reduce la prima | 82, 86 | 13 |
| Impuestos sobre primas | El 2% y el 5% de bomberos son flujos de cumplimiento; el 5% que paga el asegurado no es ingreso | B65(i), B123(a)(iii) | 3 |
| Estados intermedios | No se preparan, así que la elección de B137 no aplica | B137 | 3 |

## 3. Seguros Barú, S.A.: perfil de la entidad

Seguros Barú es una aseguradora panameña nueva que emite seguros de vida y de daños desde el 1 de enero de 2023. Como empieza el mismo día en que IFRS 17 entra en vigor (par. C1) y no tiene contratos anteriores, todos sus grupos se miden desde su reconocimiento inicial y no se aplica ninguno de los enfoques de transición (C3–C24).

| Atributo | Valor |
| --- | --- |
| Moneda funcional y de presentación | Dólar estadounidense (USD); Panamá usa el dólar junto al balboa a la par, así que no hay diferencias de cambio (par. 30) |
| Cierres | Anuales al 31 de diciembre de 2023, 2024 y 2025, sin estados intermedios |
| Capital inicial | USD 20 millones, por encima del mínimo legal de USD 5 millones del [art. 41 de la Ley 12 de 2012](https://supervalores.gob.pa/wp-content/uploads/2021/03/Ley_12_de_2012.pdf) |
| Regulador | Superintendencia de Seguros y Reaseguros de Panamá (SSRP) |
| Inversiones que respaldan vida temporal | Bonos del Tesoro de EE. UU. a valor razonable con cambios en OCI (NIIF 9) |
| Inversiones que respaldan el resto | Letras y bonos cortos del Tesoro a valor razonable con cambios en resultados (NIIF 9) |

La clasificación de las inversiones no es un detalle menor: B129 exige considerar los activos de cada portafolio al elegir si los ingresos y gastos financieros de seguros van a resultados o se desagregan en OCI (sección 14).

### Impuestos sobre primas y su tratamiento

Panamá grava las primas de tres formas, y IFRS 17 las trata distinto según quién soporta el costo. Los dos primeros son costos de la aseguradora que surgen directamente de los contratos, así que entran en los flujos de cumplimiento; B65(i) menciona de forma expresa las contribuciones a bomberos (“fire service levies”).

| Impuesto | Base | Quién lo soporta | Tratamiento IFRS 17 |
| --- | --- | --- | --- |
| 2% sobre primas ([art. 33 de la Ley 59 de 1996, modificado por el art. 98 de la Ley 10 de 2010](https://www.bomberos.gob.pa/wp-content/uploads/2015/08/ley-10-del-16-marzo2010-bomberos.pdf)) | Primas ingresadas netas de cancelaciones, todos los ramos | Aseguradora | Flujo de cumplimiento y gasto del servicio de seguros (B65(i)) |
| 5% adicional para el Cuerpo de Bomberos (misma norma) | Primas de seguros contra incendio | Aseguradora | Flujo de cumplimiento del portafolio incendio/hogar (B65(i)) |
| 5% al asegurado ([art. 63 de la Ley 12 de 2012, modificado por la Ley 65 de 2016](https://www.prensa.com/impresa/economia/un-impuesto-que-seguro-usted-paga/)) | Primas brutas, excepto incendio y vida con valores de rescate | Asegurado; la aseguradora solo retiene | Se cobra por cuenta de terceros: no es ingreso ni flujo de cumplimiento (B123(a)(iii), B124(a)(iii)); el motor modela primas netas de este impuesto |

Por simplicidad, la contribución de bomberos se aplica solo a incendio/hogar y no a Todo Riesgo Construcción, aunque esa póliza también cubre incendio. Queda anotado como supuesto simplificador.

## 4. Portafolios y productos

La aseguradora tiene cinco productos emitidos y un tratado de reaseguro cedido, diseñados para que cada uno ejercite una parte distinta de la norma. Los volúmenes y comisiones son metas iniciales para el simulador de la Fase 1, que puede ajustarlas sin cambiar las políticas de este memo.

| Portafolio | Producto | Cobertura y primas | Volumen anual objetivo | Comisión | Qué demuestra |
| --- | --- | --- | --- | --- | --- |
| Autos | Particulares y flotas comerciales (flotas ≈ 10% de la prima) | Anual; prima al inicio o hasta 4 cuotas dentro del año | 20.000 pólizas; prima media USD 600 (≈ USD 12 M) | 15% | LRC por PAA, LIC con chain ladder y Bornhuetter-Ferguson, onerosidad PAA en flotas |
| Incendio/hogar | Viviendas y pequeños comercios | Anual; prima única al inicio | 8.000 pólizas; prima media USD 500 (≈ USD 4 M) | 20% | Gastos de adquisición como gasto (59(a)) y LIC sin descontar (59(b)) |
| Todo Riesgo Construcción (TRC) | Obras civiles de 3 años; la exposición crece con el avance de obra | Prima única al inicio | 150 obras; prima media USD 20.000 (≈ USD 3 M) | 12% | Test de elegibilidad PAA frente a GMM |
| Vida temporal | Plazos de 10, 15 y 20 años; edades de emisión 25–60; suma asegurada USD 50.000–500.000 | Prima anual nivelada | 3.000 pólizas nuevas | 50% el primer año y 5% en renovaciones | CSM, unidades de cobertura, tres grupos de rentabilidad y un grupo oneroso desde el inicio |
| Vida con ahorro | Vida universal tipo B: al morir paga suma asegurada más valor de cuenta; vence a los 65 años | Prima anual; tasa acreditada declarada con mínimo garantizado de 2,5%; cargo por rescate en los años 1–5 | 1.500 pólizas; prima media USD 3.000 (≈ USD 4,5 M) | 40% el primer año | Componente de inversión, servicio de retorno de inversión (B119B) y por qué no es VFA |
| Reaseguro cedido | Cuota parte de 40% sobre vida temporal; un tratado por año de suscripción; reasegurador ficticio con calificación A | Primas cedidas con comisión de cesión de 20% | Sigue a vida temporal | — | CSM del reaseguro (65) y componente de recuperación de pérdidas (66A–66B) |

En vida temporal, un canal promocional vende en 2023 y 2024 con 20% de descuento sobre la tarifa. Ese descuento es la causa del grupo oneroso desde el inicio, y la promoción termina en 2025.

## 5. Alcance y separación de componentes

Los cinco productos y el tratado cedido están dentro del alcance de IFRS 17, y el único componente que exige análisis es el valor de cuenta de vida con ahorro, que no se separa. El razonamiento por producto es el siguiente.

- **Definición de contrato de seguro (apéndice A, B17–B23).** Autos, incendio/hogar y TRC cubren daños y responsabilidad (B26(a) y (b)); vida temporal cubre la muerte (B26(c)). En vida con ahorro, la suma asegurada que se paga además del valor de cuenta es un importe adicional significativo, así que el contrato transfiere riesgo de seguro significativo (B23).
- **Reaseguro cedido (par. 3(b)).** La cuota parte transfiere al reasegurador sustancialmente todo el riesgo de la porción cedida, lo que basta para considerar que transfiere riesgo significativo (B19).
- **Exclusiones y combinaciones (par. 7–9).** Ninguna exclusión del par. 7 aplica, no hay contratos de servicio de tarifa fija (par. 8) ni préstamos con exoneración por muerte (par. 8A), y no hay series de contratos que deban combinarse (par. 9).
- **Derivados implícitos (par. 11(a)).** La tasa mínima garantizada de 2,5% y la opción de rescate de vida con ahorro no se separan: el piso está por debajo de las tasas de mercado al emitir y ambas opciones dependen del contrato anfitrión, según los criterios de NIIF 9 (B4.3.8). Se miden dentro de los flujos de cumplimiento (B65(d)).
- **Componente de inversión (par. 11(b), B31–B32).** El valor de cuenta no es distinto, porque está altamente interrelacionado con la cobertura: si el asegurado rescata, la cobertura de muerte termina (B32(b)). Por eso se mide con IFRS 17, pero se excluye de ingresos y gastos (par. 85).
- **Medición del componente de inversión.** Se define como el valor de rescate en cada fecha, es decir, el valor de cuenta menos el cargo por rescate, porque es el importe que se paga en todas las circunstancias (apéndice A). El método se revela según el par. 117(c)(iv).
- **Bienes y servicios distintos (par. 12, B33–B35).** No hay. Autos no incluye asistencia vial: como ese servicio se vende por separado en el mercado, podría ser distinto (B34) y obligaría a separarlo con NIIF 15, lo que no aporta al objetivo del proyecto.

## 6. Nivel de agregación y reconocimiento

Cada grupo se identifica como portafolio × cohorte anual × nivel de rentabilidad, por ejemplo VT-2023-ONE, y se fija al reconocerlo sin reevaluarse después (par. 24). Con tres cohortes y hasta tres niveles por portafolio, el motor maneja como máximo 45 grupos emitidos y 3 grupos de reaseguro.

- **Portafolios (par. 14).** Autos, incendio/hogar, TRC, vida temporal y vida con ahorro son líneas con riesgos distintos y se gestionan por separado, así que forman cinco portafolios. El tratado cedido forma un portafolio de reaseguro aparte (par. 61).
- **Cohortes (par. 22).** Un grupo nunca mezcla contratos emitidos con más de un año de diferencia; la cohorte es el año calendario de emisión.
- **Conjuntos de contratos (par. 17).** En los portafolios GMM se evalúan celdas homogéneas (producto, plazo, banda de edad y canal) en lugar de pólizas individuales, porque hay información razonable de que cada celda cae completa en un mismo grupo.
- **Par. 20.** No se aplica, porque ninguna ley restringe la tarificación de estos productos; por eso tampoco hay revelación del par. 126 sobre este punto.

### Reglas de clasificación por rentabilidad (par. 16–19, 47)

| Modelo | Oneroso | Sin posibilidad significativa de volverse oneroso | Resto |
| --- | --- | --- | --- |
| GMM (vida temporal, vida con ahorro, TRC) | Flujos de cumplimiento más gastos de adquisición dan una salida neta al reconocer (par. 47) | Sigue sin ser oneroso bajo el estrés combinado: mortalidad +15%, caducidad ±30% en la dirección adversa y gastos +10% (par. 19(a)) (propuesta) | No es oneroso, pero sí lo sería bajo ese estrés |
| PAA (autos, incendio/hogar) | Se presume que no hay onerosos salvo que los hechos lo indiquen (par. 18); indicador: ratio combinado esperado con ajuste por riesgo mayor que 100% | Ratio combinado esperado de 95% o menos (propuesta) | Ratio entre 95% y 100% |

Con estas reglas, el canal promocional de vida temporal cae en el grupo oneroso de 2023 y 2024, y flotas comerciales cae en el grupo “resto” de autos en 2023 y 2024. En 2025, la experiencia de 2024 es un hecho que indica onerosidad, así que flotas nace onerosa (par. 18).

### Reconocimiento

- **Grupos emitidos (par. 25).** La cobertura empieza el día de emisión y la primera prima vence ese mismo día, así que la fecha de reconocimiento es la de emisión. Los grupos siguen abiertos hasta el 31 de diciembre y en cada cierre solo incluyen los contratos ya emitidos (par. 28).
- **Reaseguro (par. 62 y 62A).** Cada tratado empieza el 1 de enero, pero como da cobertura proporcional, su reconocimiento se retrasa hasta que se reconoce la primera póliza subyacente.
- **Activo por flujos de adquisición (par. 28A–28F, B35A).** No surge, porque las comisiones se pagan al emitir y no antes, y las comisiones de renovación se pagan en cada renovación, sin anticipos atribuibles a renovaciones futuras.

## 7. Elección del modelo de medición

Autos e incendio/hogar van a PAA por su plazo, vida y reaseguro van a GMM, y TRC queda en manos del test de elegibilidad. Ningún producto cumple las condiciones de VFA.

| Portafolio | Modelo | Motivo |
| --- | --- | --- |
| Autos | PAA | La cobertura es de un año y la renovación se retarifica, así que el límite del contrato termina al año (par. 34(a), 53(b)) |
| Incendio/hogar | PAA | Mismo motivo (par. 53(b)) |
| TRC | PAA o GMM, según el test | La cobertura dura 3 años, así que solo cabe el criterio de no diferir materialmente (par. 53(a), 54) |
| Vida temporal | GMM | Cobertura larga y sin participación en elementos subyacentes |
| Vida con ahorro | GMM | No cumple B101 (ver abajo) |
| Reaseguro cedido | GMM | El tratado cubre las pólizas de cada año durante todo su plazo de 10 a 20 años, así que no cumple el par. 69(b), y su duración descarta el 69(a) (par. 70(b)); además, el reaseguro nunca puede ser VFA (B109) |

### Test de elegibilidad PAA para TRC (par. 53(a) y 54)

1. Al iniciar cada grupo se proyecta el LRC con PAA y con GMM en cada cierre futuro hasta el fin de la cobertura.
2. La proyección se repite en escenarios razonablemente posibles: base, siniestralidad ±20%, tasas ±100 pb y avance de obra más lento o más rápido. Esto responde al par. 54, que descarta el PAA si se espera variabilidad significativa antes de que ocurra un siniestro.
3. El grupo es elegible si en todos los escenarios y cierres la diferencia absoluta entre ambos LRC es de 5% del LRC del GMM o menos (umbral confirmado).
4. El resultado se documenta por cohorte. Como la exposición crece con el avance de obra, un PAA lineal en el tiempo tiende a liberar ingreso antes que el GMM; si TRC resultara elegible, el ingreso se distribuiría según el patrón esperado de siniestros (B126(b)).

El motor GMM de la Fase 3 se construye para TRC en cualquier caso, porque el test necesita ambas mediciones.

### Por qué vida con ahorro no es VFA (B101)

La tasa acreditada la declara la aseguradora al final de cada periodo, tomando como referencia el rendimiento de su cartera, pero el contrato no especifica un conjunto identificado de elementos subyacentes. B106(b) describe exactamente este caso: una tasa de interés acreditada fijada al final del periodo no constituye un conjunto claramente identificado. Sin ese conjunto falla la condición B101(a), y las condiciones B101(b) y (c) no pueden cumplirse sin ella. La evaluación se hace al inicio y no se repite salvo modificación del contrato (B102).

### Opciones dentro del PAA

- **Gastos de adquisición (par. 59(a)).** Autos los resta del LRC y los amortiza durante la cobertura (par. 55(a)(ii) y 55(b)(iii)), con ingreso y gasto iguales según B125. Incendio/hogar los reconoce como gasto al incurrirlos, lo que se permite porque la cobertura no supera un año. Elegir distinto en cada portafolio permite comparar ambos efectos en el proyecto.
- **Componente de financiación (par. 56).** No se ajusta el LRC, porque entre cada parte del servicio y la prima correspondiente no pasa más de un año.
- **Descuento del LIC (par. 59(b)).** Autos descuenta su LIC, porque la responsabilidad civil por lesiones se liquida en varios años. Incendio/hogar no descuenta los flujos que se pagan dentro del año siguiente a la ocurrencia y sí descuenta los pocos que se pagan después. Por coherencia, el test de onerosidad de incendio/hogar tampoco descuenta esos flujos (par. 57(b)).
- **Patrón de ingresos (B126).** Autos e incendio/hogar liberan la prima según el paso del tiempo, porque su riesgo es uniforme durante el año.

## 8. Curva de descuento

La curva se construye de abajo hacia arriba (bottom-up, B80): una curva líquida libre de riesgo en dólares, la TNC del Tesoro, más una prima de iliquidez por plazo que sale de la curva corporativa HQM y depende de cuán líquido es cada portafolio. Así se cumple el par. 36, que pide reflejar el valor temporal del dinero, las características de los flujos y su liquidez.

1. **Curva base: TNC de fin de mes.** Son las tasas spot de la curva de cupones nominales del Tesoro (TNC), que el Tesoro publica cada medio año de 0,5 a 100 años, con capitalización semestral. Se usa la versión de fin de mes de diciembre de 2023, 2024 y 2025, porque refleja las condiciones a la fecha de medición (par. 33(c), B54). Más allá de 30 años, el Tesoro mantiene constante la tasa forward en su promedio de 15 a 30 años, así que no hace falta otra extrapolación. Los bonos del Tesoro tienen un riesgo de crédito nulo o insignificante, como pide B79.
2. **Prima de iliquidez por plazo (B80).** Para cada plazo se toma la diferencia entre la curva HQM de fin de mes (bonos corporativos AAA–A, publicada por el Tesoro) y la TNC.
3. **Política elegida: curva HQM.** Se suma el diferencial completo, sin deducir la parte de crédito y con el mismo factor para todos los portafolios. Como TNC + (HQM − TNC) = HQM, la curva de descuento es la HQM. Es un juicio contable: el diferencial incluye compensación por riesgo de crédito, que B79 pide excluir (B84(b) por analogía), así que se revela la sensibilidad a deducirla (par. 117(c)(iii), 128).
4. **Opciones disponibles en el motor.** Se puede deducir un porcentaje de crédito (la referencia es 55%, ver abajo) y graduar la prima por liquidez del pasivo con factores de 100%, 75% y 50% (tabla abajo). Ambas son parámetros del motor y del libro de Excel.
5. **Curva mensual.** La curva se convierte a tasa anual efectiva y se interpola a plazos mensuales, de 1 a 1.200 meses, de forma lineal sobre el logaritmo del factor de descuento (forward constante dentro de cada semestre). Por debajo de 6 meses se mantiene la tasa de 0,5 años.
6. **Control cruzado.** La curva par diaria del Tesoro, calibrada con Smith-Wilson, se usa solo para comprobar la TNC hasta 30 años.
7. **Tasas bloqueadas (B72(b), B72(c), B73).** Para cada grupo GMM se promedian las curvas de fin de mes del año de emisión, ponderadas por la prima emitida en cada mes. Como los grupos siguen abiertos hasta fin de año, el promedio se recalcula al agregar contratos (par. 28). Esa misma curva sirve para la acreción del CSM, para medir sus ajustes y para el resultado financiero en resultados de vida temporal con OCI (B72(e)(i)).
8. **Coherencia (B74).** Los flujos nominales, con inflación de gastos incluida, se descuentan a tasas nominales. En vida con ahorro, la tasa acreditada futura se proyecta con las tasas forward de la misma curva, para que flujos y descuento reflejen la misma variabilidad (B74(b)).

| Liquidez | Portafolios | Factor graduado (opción; la política usa 100%) | Razón |
| --- | --- | --- | --- |
| Alta iliquidez | Vida temporal y su reaseguro | 100% | No hay valor de rescate: la aseguradora no puede ser obligada a pagar antes de la muerte; el reaseguro usa supuestos coherentes con el subyacente (par. 63) |
| Media | LIC de autos, incendio/hogar y TRC | 75% | Los siniestros se pagan al liquidarse y no pueden adelantarse, pero los plazos son cortos |
| Baja | Vida con ahorro | 50% | El asegurado puede exigir el valor de rescate en cualquier momento |

### Cómo se calcula el porcentaje de crédito (para revisiones futuras)

IFRS 17 no fija un porcentaje (B78). Pide maximizar los datos observables (B78(a)), excluir el riesgo de crédito (B79) y sugiere el precio de los derivados de crédito como referencia (B85). Aunque la política actual no lo deduce, el porcentaje se calcula cada año para la revelación de sensibilidad:

1. **Participación del incumplimiento según CDS.** Para cada calificación, prima del CDS ÷ diferencial del bono sobre el Tesoro. [Longstaff, Mithal y Neis (2005)](https://www.nber.org/system/files/working_papers/w10418/w10418.pdf) midieron 51% en AAA/AA y 56% en A.
2. **Ponderación por calificación.** Porcentaje = Σ peso de la calificación en la muestra HQM × su participación. Con una muestra de 20% AAA/AA y 80% A, el resultado es 55%.
3. **Piso de pérdida esperada.** Porcentaje mínimo = probabilidad anual de incumplimiento de un bono A × severidad ÷ diferencial, con datos de estudios públicos de incumplimiento. Se usa el mayor entre los pasos 2 y 3. Con 0,08% × 60% ÷ 74 pb, el piso es 6,5%.
4. **Consistencia.** Se aplica el mismo porcentaje en todos los cierres salvo evidencia nueva (B54–B55).
5. **Revelación.** Se describen el método (par. 117(c)(iii)), las curvas (par. 120) y la sensibilidad del pasivo al porcentaje (par. 128).

La mezcla de calificaciones, la probabilidad y la severidad del ejemplo son ilustrativas. El cálculo está en `illiquidity.py` (funciones `credit_share_from_cds` y `expected_loss_floor`) y en la hoja Metodo\_credito del libro de Excel.

**Resultado con los archivos del Tesoro.** El diferencial HQM − TNC a 10 años fue de 116 pb en 2023, 78 pb en 2024 y 74 pb en 2025. Con la política elegida, la curva de descuento a 20 años es 5,18%, 5,84% y 5,84% en los tres cierres; con la opción de 55% de crédito sería 4,72%, 5,41% y 5,43%. El control cruzado con Smith-Wilson difiere a lo sumo 12,6 pb de la TNC hasta 30 años.

En la revelación del par. 120 se mostrarán las curvas por cierre y nivel de liquidez a 1, 5, 10, 20, 30 y 40 años.

## 9. Supuestos no financieros

Todos los supuestos son estimaciones de mejor estimación, sin márgenes de prudencia, porque los flujos deben ser el valor esperado e insesgado de todos los resultados posibles (par. 33(a), B37–B38). La prudencia vive solo en el ajuste por riesgo, para no contarla dos veces (B90). Cada cierre se actualizan con la nueva evidencia, dándole más peso a la más persuasiva (B54–B57).

### Mortalidad (vida temporal y vida con ahorro)

- **Base:** tabla CSO 1980 por sexo y edad. Se usa la versión agregada (fumadores y no fumadores), con edad al cumpleaños más cercano: tablas 42 (hombres) y 36 (mujeres) de la Society of Actuaries.
- **Mejor estimación (par. 33, B49–B50):** CSO 1980 × factor de experiencia. El factor inicial es 75%, que representa a una población asegurada seleccionada y es un parámetro sintético. En cada cierre se compara la mortalidad real con la esperada y el factor se actualiza ponderando por credibilidad, en lugar de saltar a la experiencia del año (B56–B57). Como una aseguradora nueva tiene pocas muertes, su experiencia propia se combina con el estudio que el reasegurador entrega en cada cierre, con credibilidad Z = √(muertes / 1.082) (B41(c)). En 2023 hubo 6 muertes y Z fue 7%.
- **Tendencia (B58):** mejora de mortalidad de 1% anual, con sensibilidad a 0%.
- **Reserva de tipo estatutario para comparar:** reserva de prima neta con CSO 1980 al 100% y tasa técnica fija de 4% (propuesta). Es una base ilustrativa y conservadora, no una réplica de la regulación panameña; sirve para mostrar cómo IFRS 17 traslada esa prudencia implícita al ajuste por riesgo y al CSM.

### Caducidad

- **Vida temporal:** 8% el primer año, 6% el segundo y 4% desde el tercero.
- **Vida con ahorro:** 10% el primer año, bajando hasta 4% en el sexto, con un repunte el año en que termina el cargo por rescate. Una caducidad dinámica ligada a las tasas de mercado (B53) se evalúa en la Fase 5.

### Gastos

- **Adquisición:** comisiones de la sección 4 más un costo de suscripción por póliza.
- **Mantenimiento:** costo fijo por póliza y año, con inflación de 2,5% anual. Como esa inflación es una expectativa propia de la entidad y no un índice de mercado, no es un supuesto financiero (B128(b)); sus cambios ajustan el CSM.
- **Manejo de siniestros:** porcentaje de los siniestros en daños y costo fijo por siniestro en vida (B65(f)).
- **Gastos generales:** la parte atribuible al cumplimiento de contratos se asigna por primas (B65(l)); 20% no es atribuible (desarrollo de productos, capacitación) y se reconoce como gasto fuera del resultado del servicio de seguros (B66(d)).
- **Impuestos sobre primas:** según la sección 3.

### Siniestros de daños y construcción

- **Simulación:** frecuencia Poisson y severidad lognormal por póliza, con retraso de reporte y patrón de pago. La inflación de severidad (por ejemplo, repuestos en autos) es una expectativa propia, no financiera (B128(b)).
- **Calibración:** el [CAS Loss Reserving Database](https://www.casact.org/publications-research/research/research-resources/loss-reserving-data-pulled-naic-schedule-p) trae seis líneas de Schedule P, años de accidente 1988–1997 (la versión que distribuye el paquete chainladder) y 10 años de desarrollo. Autos particulares usa Private Passenger Auto Liability y flotas usa Commercial Auto Liability. Esa base no tiene línea de propiedad, así que daños propios de autos, incendio/hogar y TRC usan patrones cortos fijados como supuesto documentado.
- **Estimación del LIC:** al cierre de 2023 la aseguradora tiene un solo año de accidente, y al de 2025 tiene tres. Con tan poca historia, B41(c) permite complementar los datos propios con supuestos y datos externos. El LIC suma las reservas de caso de los siniestros reportados y un IBNR tipo Bornhuetter-Ferguson: los siniestros esperados de cada mes de ocurrencia, con la mejor estimación del cierre, por la proporción que aún no se ha reportado según el retraso de reporte supuesto. Se agrega 3% de gastos de liquidación (B65(f)). Los pagos futuros siguen los patrones del CAS en responsabilidad civil y los retrasos supuestos en las coberturas cortas, y con ellos se descuenta el LIC. En la retrospectiva con los pagos simulados posteriores, autos queda dentro de ±15% en los tres cierres.
- **Catástrofes (B39):** incendio/hogar incluye en el valor esperado una carga por terremoto e inundación con probabilidad insesgada, aunque la semilla no genere ningún evento.

## 10. Ajuste por riesgo no financiero

El ajuste por riesgo usa costo de capital de 6% en vida y el percentil 75 en daños y construcción, y en ambos casos se revela el nivel de confianza resultante (par. 119). Mide la compensación que la entidad exige por la incertidumbre de riesgo de seguro, caducidad y gastos (par. 37, B86), y excluye el riesgo operacional general (B89).

| Portafolio | Técnica | Cómo se calcula |
| --- | --- | --- |
| Vida temporal y vida con ahorro | Costo de capital | 6% × valor presente del capital proyectado para riesgos no financieros. El capital se proyecta en proporción a la suma asegurada en vigor esperada. El capital es el VaR a un año al 99,5% de los choques de mortalidad (+15%), caducidad (±50%, el peor) y gastos (+10% e inflación +1 pp), agregados con una matriz de correlación inspirada en la fórmula estándar de Solvencia II |
| Autos, incendio/hogar y TRC | Nivel de confianza | Percentil 75 menos la media de la distribución del valor presente de los siniestros. La forma es lognormal. En el LIC, el coeficiente de variación de la responsabilidad civil sale de un ajuste log-lineal del CV de Mack contra el tamaño de la reserva, sobre 96 compañías (autos particulares) y 92 (flotas) del CAS; en las coberturas cortas es un supuesto (15% a 40%). En la cobertura restante se usan CV supuestos por segmento (8% a 35%). Las coberturas se agregan con correlación de 25% y el total se reparte en proporción al ajuste individual |
| Reaseguro cedido | Riesgo transferido (par. 64) | Ajuste por riesgo de vida temporal bruto menos el neto de reaseguro |

- **Diversificación (B88(a)).** Se reconoce entre riesgos y productos dentro de vida y dentro de daños, pero no entre vida y daños, por prudencia y simplicidad. El total diversificado se asigna a los grupos en proporción a su ajuste individual.
- **Nivel de confianza equivalente (par. 119, B92).** Para vida, la distribución del valor presente de los flujos no financieros se aproxima con una normal cuya desviación se deduce del VaR al 99,5%; el nivel equivalente es la probabilidad acumulada del ajuste. Luego se combina con daños para revelar un nivel de la entidad.
- **Sin desagregación (par. 81).** Todo el cambio del ajuste por riesgo va al resultado del servicio de seguros, y así se revela (par. 117(c)(ii)).
- **Pruebas de propiedades (B91).** El motor incluye pruebas automáticas que verifican que el ajuste crece con la duración y la dispersión, y que disminuye cuando la experiencia reduce la incertidumbre.

## 11. Medición inicial y onerosidad

Al reconocer un grupo GMM, el motor calcula los flujos de cumplimiento y fija el CSM para que no surja ganancia; si los flujos son una salida neta, reconoce la pérdida de inmediato y crea un componente de pérdida. En PAA, el LRC parte de las primas recibidas y la onerosidad se prueba cuando los hechos lo indican.

**Convención de signos del motor:** los pasivos son positivos, los flujos de cumplimiento se calculan como valor presente de salidas menos valor presente de entradas más ajuste por riesgo, y el CSM nunca es negativo en contratos emitidos.

| Elemento | GMM (vida y TRC si aplica) | PAA (autos e incendio/hogar) | Reaseguro cedido |
| --- | --- | --- | --- |
| Medición inicial | Flujos de cumplimiento más CSM (par. 32) | Primas recibidas menos gastos de adquisición, salvo que se reconozcan como gasto (par. 55(a)) | Flujos de cumplimiento más CSM (par. 63–65) |
| CSM inicial | Monto que evita una ganancia al reconocer flujos y cobros de esa fecha (par. 38) | No existe | Costo o ganancia neta de comprar reaseguro (par. 65), incluido el ingreso del par. 66A |
| Onerosidad al inicio | Si flujos de cumplimiento, gastos de adquisición previos y cobros dan salida neta: pérdida en resultados, CSM igual a cero y componente de pérdida (par. 47, 49) | Se presume que no hay, salvo hechos que lo indiquen (par. 18) | No aplica: el reaseguro cedido no puede ser oneroso (par. 68) |
| Onerosidad posterior | Cambios desfavorables de servicio futuro que superan el CSM (par. 48) | Si los hechos lo indican, flujos de la cobertura restante contra el LRC; la diferencia es pérdida (par. 57–58) | Componente de recuperación de pérdidas (par. 66(c), 66B) |

- **Contratos agregados durante el año (par. 28, 44(a)).** El motor reconoce cada mes de emisión por separado y suma sus efectos en el grupo. El CSM de los contratos nuevos se mide con la tasa bloqueada del grupo.
- **Reaseguro y pérdidas iniciales (par. 66A, B119C–B119D).** Como cada tratado se firma antes de emitir las pólizas que cubre, cuando el grupo promocional de vida temporal nace oneroso el reaseguro reconoce un ingreso igual a la pérdida × 40% (la proporción de siniestros que se espera recuperar).
- **Revelación de negocio nuevo (par. 107–108).** Por cierre se muestran valor presente de salidas (con gastos de adquisición aparte), de entradas, ajuste por riesgo y CSM, separando los grupos onerosos.

## 12. Medición posterior: guion de los tres cierres

En cada cierre el valor en libros de un grupo es el LRC (flujos de servicio futuro más CSM) más el LIC (par. 40). Lo que cambia la historia de cada año son los eventos guionizados de la tabla, elegidos para que cada mecanismo de la norma aparezca al menos una vez.

### Reglas de movimiento

- **CSM sin participación directa (par. 44).** Saldo inicial más contratos nuevos, más intereses a la tasa bloqueada (B72(b)), más cambios de flujos de servicio futuro medidos a tasa bloqueada (B96, B72(c)), menos la liberación por unidades de cobertura (par. 44(e), B119).
- **Lo que no toca el CSM (B97).** Los cambios de tasas van a ingresos o gastos financieros; los cambios del LIC van a gastos del servicio; los ajustes por experiencia van a resultados, salvo las primas que se refieren a servicio futuro (B96(a)). En vida con ahorro, la diferencia entre el componente de inversión esperado y el real sí ajusta el CSM (B96(c)).
- **Componente de pérdida (par. 49–52).** Los cambios del par. 51 se reparten entre el componente de pérdida y el resto del LRC en proporción al peso del componente de pérdida en el valor presente de las salidas al inicio del periodo, para que llegue a cero al final de la cobertura (par. 52). Las mejoras posteriores van primero al componente de pérdida (par. 50(b)).
- **Unidades de cobertura (B119, B119A–B119B).** Vida temporal usa la suma asegurada en vigor esperada. Vida con ahorro suma el cargo esperado por riesgo de muerte y una tarifa de 1% sobre el valor de cuenta, que representa el servicio de retorno de inversión; esta ponderación se revela según el par. 117(c)(v). TRC, si va a GMM, usa la exposición esperada por avance de obra. Las unidades no se descuentan (propuesta).
- **PAA (par. 55(b), 42).** El LRC suma primas recibidas, resta gastos de adquisición y la prima devengada; el LIC se mueve por siniestros incurridos, pagos, cambios de estimación y finanzas.

### Eventos guionizados

| Cierre | Evento | Grupo afectado | Efecto contable | Párrafos |
| --- | --- | --- | --- | --- |
| 2023 | Reconocimiento inicial de todas las cohortes 2023; el canal promocional nace oneroso | VT-2023-ONE | Pérdida inicial, componente de pérdida e ingreso por recuperación del reaseguro | 47, 49, 66A |
| 2023 | Flotas comerciales se clasifica en “resto”, sin pérdida | AUTO-2023-RES | Ninguno al inicio | 16, 18 |
| 2023 | Primer año de accidente; LIC por Bornhuetter-Ferguson | Autos, incendio/hogar | LIC con ajuste por riesgo al percentil 75 | 59(b), B41(c) |
| 2024 | La experiencia de mortalidad de edades altas con suma asegurada alta es peor de lo esperado; el factor de experiencia sube | VT-2023-RES | El aumento de flujos supera el CSM: el grupo se vuelve oneroso y nace un componente de pérdida | 48, 49 |
| 2024 | El mismo cambio afecta los flujos del reaseguro | RE-2023 | La parte ligada a la pérdida del subyacente no ajusta el CSM del reaseguro: va a resultados y crea un componente de recuperación; el resto sí ajusta el CSM | 66(c)(i), 66B |
| 2024 | La inflación de repuestos sube la severidad de flotas | AUTO-2024-RES | Test de onerosidad PAA con pérdida en el LRC | 57–58 |
| 2024 | Cambia la curva del Tesoro respecto de 2023 | Todos los descontados | Flujos remedidos; efecto en finanzas (OCI en vida temporal), sin tocar el CSM | 87, 88, B97(a) |
| 2025 | La nueva evidencia mejora la mortalidad; el factor baja | VT-2023-RES | Reversión: primero se anula el componente de pérdida y el exceso reconstruye el CSM | 50(b), 44(c)(ii) |
| 2025 | La experiencia de 2024 indica que flotas nace onerosa | AUTO-2025-ONE | Grupo oneroso desde el inicio en PAA | 16(a), 18, 57 |
| 2025 | Termina la promoción de vida temporal | VT-2025 | La cohorte 2025 solo tiene grupos rentables | 16 |
| 2025 | Tercer año de accidente | Autos | Triángulo de desarrollo de tres años en revelaciones | 130 |

Los tamaños de los choques de mortalidad se calibran en la Fase 2 para que el aumento de 2024 supere el CSM del grupo y la mejora de 2025 supere el componente de pérdida.

## 13. Reaseguro cedido

Cada año, Seguros Barú cede el 40% de su vida temporal mediante un tratado de cuota parte que cubre las pólizas emitidas ese año durante todo su plazo. El tratado se mide con GMM, nunca puede ser oneroso (par. 68) y su gran prueba es el componente de recuperación de pérdidas.

- **Términos.** La prima cedida es el 40% de la prima bruta; el reasegurador devuelve una comisión de cesión fija de 20% de esa prima y paga el 40% de cada siniestro. No hay comisión de utilidades.
- **Grupos y reconocimiento (par. 61, 62A).** Cada tratado anual es un grupo de un solo contrato, clasificado por ganancia o costo neto al inicio. Se reconoce cuando se emite la primera póliza cubierta.
- **Supuestos coherentes (par. 63).** Usa la misma mortalidad, caducidad y curva que vida temporal, y agrega el riesgo de incumplimiento del reasegurador: probabilidad de impago según su calificación A y una pérdida dado el impago fijada en la Fase 1. Los cambios en ese riesgo no ajustan el CSM (par. 67).
- **CSM del reaseguro (par. 65–66).** Representa el costo o ganancia neta de comprar la cobertura. Se acrecienta a la tasa bloqueada, se ajusta por cambios de servicio futuro medidos a esa tasa (B72(c)) y se libera según la suma asegurada cedida en vigor.
- **Componente de recuperación de pérdidas (par. 66A–66B, B119C–B119F).** Nace en 2023 y 2024 junto con los grupos promocionales onerosos, por pérdida × 40%, y en 2024 por la parte de pérdida del grupo VT-2023-RES. Después sigue al componente de pérdida del subyacente, con un tope igual a la parte que se espera recuperar (B119F).
- **Presentación (par. 82, 86).** Se presenta aparte de los contratos emitidos y se elige mostrar por separado los importes recuperados y la asignación de primas pagadas. La comisión de cesión no depende de los siniestros, así que reduce las primas pagadas (86(b)); las recuperaciones de pérdidas cuentan como importes recuperados (86(ba)); nada de esto reduce los ingresos por seguros (86(c)).
- **Finanzas.** Sigue la misma elección de OCI que vida temporal (par. 88(b)), para que la cesión no cree una asimetría contable entre lo bruto y lo cedido.

## 14. Presentación en los estados financieros

Los estados separan el resultado del servicio de seguros del resultado financiero, presentan el reaseguro aparte y llevan a OCI solo los efectos de tasas de vida temporal y su reaseguro. Se preparan con NIC 1, porque IFRS 18 rige desde 2027.

### Elección de OCI por portafolio (par. 88, B129)

| Portafolio | Opción | Activos que lo respaldan | Razón |
| --- | --- | --- | --- |
| Vida temporal y su reaseguro | Desagregar: en resultados a tasa bloqueada y la diferencia en OCI (par. 88(b), 90) | Bonos del Tesoro a valor razonable con cambios en OCI | Activos y pasivos llevan su volatilidad de tasas al mismo lugar. Los cambios financieros no alteran los pagos al asegurado, así que la tasa bloqueada es la asignación sistemática (B131, B72(e)(i)) |
| Vida con ahorro | Todo en resultados (par. 88(a)) | Valor razonable con cambios en resultados | La tasa acreditada sigue a las tasas de mercado; con OCI habría que usar la tasa efectiva de B132, y con activos y pasivos a valores corrientes en resultados la compensación es natural |
| Autos, incendio/hogar y TRC | Todo en resultados (par. 88(a)) | Letras y bonos cortos a valor razonable con cambios en resultados | Duraciones cortas y activos a valor corriente en resultados |

### Estado de situación financiera (par. 78–79)

Se presentan por separado, a nivel de portafolio, los contratos emitidos que son activos, los que son pasivos y lo mismo para el reaseguro cedido. El patrimonio muestra capital, resultados acumulados y dos reservas de OCI: la de finanzas de seguros y la de valor razonable de inversiones.

### Estado de resultados (par. 80–86)

1. **Ingresos por seguros (par. 83).** En GMM, la suma de siniestros y gastos esperados, liberación del ajuste por riesgo, liberación del CSM, ajustes por experiencia de primas y recuperación de gastos de adquisición (B121–B125). En PAA, la prima esperada asignada por paso del tiempo (B126).
2. **Gastos del servicio de seguros (par. 84).** Siniestros y gastos incurridos, amortización de gastos de adquisición, pérdidas y reversiones de grupos onerosos y cambios del LIC.
3. **Resultado neto del reaseguro (par. 82, 86).** Importes recuperados menos asignación de primas pagadas, en una línea aparte.
4. **Resultado financiero.** Ingresos de inversiones (NIIF 9) frente a ingresos y gastos financieros de seguros emitidos y cedidos (par. 87).
5. **Otros gastos.** Gastos no atribuibles a contratos (B66(d)).

Los componentes de inversión de vida con ahorro, es decir, rescates y vencimientos hasta el valor de rescate, no aparecen ni en ingresos ni en gastos (par. 85). El impuesto sobre la renta queda fuera del alcance del proyecto: el resultado se presenta antes de impuestos y no se registran impuestos corrientes ni diferidos (NIC 12).

## 15. Revelaciones que producirá el motor

El motor genera cada revelación como tabla exportable a Excel y la mayoría alimenta el dashboard. Las conciliaciones se presentan por separado para contratos emitidos y reaseguro cedido (par. 98) y cuadran con los saldos del estado de situación financiera (par. 99).

| Revelación | Párrafos | Alcance en Seguros Barú |
| --- | --- | --- |
| Conciliación LRC sin componente de pérdida, componente de pérdida y LIC | 100, 103–105 | Todos los portafolios; en PAA, el LIC separa valor presente y ajuste por riesgo (100(c)) |
| Conciliación de valor presente de flujos, ajuste por riesgo y CSM | 101, 104–105 | Vida temporal, vida con ahorro, TRC si va a GMM y reaseguro |
| Análisis de ingresos por seguros | 106 | Portafolios GMM |
| Efecto del negocio nuevo | 107–108 | Portafolios GMM, separando grupos onerosos |
| Liberación esperada del CSM | 109 | Bandas de 1, 2, 3, 4, 5, 6–10 y más de 10 años, emitidos y cedidos por separado |
| Explicación de ingresos y gastos financieros | 110 | Relación con el rendimiento de las inversiones de cada portafolio |
| Revelaciones propias del PAA | 97 | Criterio 53(a) o 53(b) cumplido, descuento (56, 57(b), 59(b)) y método de gastos de adquisición (59(a)) |
| Juicios y métodos | 117–118 | Supuestos, componente de inversión, ponderación de unidades de cobertura y método de OCI |
| Nivel de confianza del ajuste por riesgo | 119 | Por técnica y para la entidad |
| Curvas de descuento | 120 | Por cierre y nivel de liquidez |
| Marco regulatorio | 126 | Capital mínimo de la Ley 12 de 2012 |
| Concentraciones de riesgo | 127 | Por producto y por reasegurador único |
| Sensibilidades | 128 | Mortalidad, caducidad y gastos ±10%, siniestros de daños ±5% y tasas ±100 pb; efecto en resultados y patrimonio, antes y después del reaseguro (128(a)(i)) |
| Desarrollo de siniestros | 130 | Autos y TRC desde 2023, conciliado con el LIC; incendio/hogar no se incluye porque su incertidumbre se resuelve en un año |
| Riesgo de crédito | 131 | Exposición máxima y calidad crediticia del reasegurador |
| Riesgo de liquidez | 132 | Vencimientos de flujos netos para cada uno de los primeros cinco años y en conjunto después; se excluye el LRC medido con PAA (132(b)) |

## 16. Arquitectura del repositorio y plan de validación

El repositorio separa un motor en Python, escrito en inglés, de los notebooks y el memo en español. Antes de medir a Seguros Barú, el motor debe reproducir los ejemplos ilustrativos del IASB.

&#91;embedded content: arquitectura del motor · 6 etapas y pruebas\]

Cada fase del brief construye una etapa; las pruebas automáticas validan los motores antes de que los cierres usen sus resultados.

### Estructura propuesta del repositorio ifrs17-seguros-baru

- `src/ifrs17/`: paquete del motor con los módulos curves, assumptions, simulate, grouping, gmm, paa, lic, reinsurance, closing y reporting.
- `tests/`: pruebas con pytest, incluidas las de los ejemplos del IASB y las de propiedades del ajuste por riesgo.
- `data/`: fuentes públicas descargadas y datos sintéticos generados con semilla fija.
- `notebooks/`: un notebook narrativo por capítulo, en español.
- `docs/`: este memo en Markdown y un resumen en inglés.
- `excel/`: conciliaciones exportadas.
- `site/`: página de GitHub Pages con el dashboard de balance, resultados y cascada del CSM.

### Validación con los ejemplos ilustrativos del IASB

Una prueba pasa cuando el motor, con los mismos datos de entrada, reproduce las tablas del IASB a la unidad. La lista sale de los [ejemplos ilustrativos de IFRS 17](https://www.ifrs.org/content/dam/ifrs/publications/html-standards/english/2024/issued/ifrs17-ie.html).

| Ejemplo del IASB | Qué valida | Fase |
| --- | --- | --- |
| 1A y 1B (IE4–IE11) | Medición inicial de un grupo rentable y de uno oneroso | 2–3 |
| 2A y 2B (IE12–IE28) | Medición posterior, incluido un grupo que se vuelve oneroso | 3 |
| 3A y 3B (IE29–IE41) | Presentación en el estado de resultados | 3 |
| 4 (IE43–IE50) | Separación de componentes con saldo de cuenta | 5 |
| 6 (IE56–IE71) | Rasgos adicionales del CSM | 3 |
| 7 (IE72–IE80) | Flujos de adquisición | 3–4 |
| 8 (IE81–IE98) | Reversión de pérdidas de un grupo oneroso | 3 |
| 10 (IE113–IE123) | PAA | 4 |
| 11 y 12A–12C (IE124–IE138O) | Reaseguro cedido y componente de recuperación de pérdidas | 5 |
| 15 (IE152–IE172) | Asignación sistemática de finanzas entre resultados y OCI | 6 |

Los ejemplos 5, 9, 13, 14 y 16–18 no se usan, porque tratan servicios distintos, VFA, contratos adquiridos y transición, que están fuera del alcance. Al cierre de la Fase 6, el motor reproduce los Ejemplos 1A, 1B, 2A, 2B, 7, 8 y 12C (tests/test\_gmm\_iasb\_examples.py), con una tolerancia de una o dos unidades porque el IASB redondea los importes intermedios. Quedan por codificar los Ejemplos 3, 4, 6, 10, 11, 12A–12B y 15.

## 17. Pendientes y próximos pasos

El umbral de 5% de TRC y la exclusión del impuesto sobre la renta ya están confirmados, y el proyecto ya no depende de los acuerdos de la SSRP. La Fase 0 se cierra cuando revises las propuestas restantes; mientras tanto, la Fase 1 arranca con el módulo de curvas, que no depende de ellas.

- [ ] Revisar las propuestas restantes: estrés de clasificación de grupos, ratios combinados de 95% y 100%, unidades de cobertura sin descontar (ver anexo B), elección de OCI y tasa técnica de 4% de la reserva de comparación.
- [ ] Fase 1: listas las curvas, la CSO 1980, los patrones CAS y el simulador; las Fases 2 a 6 también están implementadas (sección 18); falta revisar las decisiones de implementación de la sección 18.
- [ ] Fase 5: decidir si el valor temporal de la garantía de 2,5% de vida con ahorro se mide con escenarios estocásticos o se documenta como inmaterial (B48, B75).
- [ ] Exportar este memo a Markdown en docs/ del repositorio, con un resumen en inglés, y publicar el repositorio y el dashboard en GitHub Pages (Fase 7).

## 18. Implementación de las Fases 1 a 6: decisiones y resultados

El motor mide los cinco portafolios y el tratado cedido en los tres cierres, y los estados financieros cuadran: activos menos pasivos es igual al patrimonio en 2023, 2024 y 2025, con diferencia cero. Hay 95 pruebas automáticas que pasan, el libro `excel/Cierres_IFRS17_Seguros_Baru.xlsx` tiene 92 celdas de control en cero, y los notebooks 02 a 07 cuentan cada fase.

Al implementar hubo que tomar decisiones que el memo dejaba abiertas o que solo aparecen al programar. Están en la tabla siguiente para que las revises; cambiar cualquiera de ellas es un parámetro en `src/ifrs17/assumptions.py` o en el módulo indicado.

### Decisiones tomadas al implementar (para revisar)

| Tema | Decisión | Párrafos |
| --- | --- | --- |
| Clasificación en GMM | Se clasifica cada celda (plazo × banda de edad × canal) reconocida en cada mes, con los supuestos del cierre anterior, la curva de fin del mes de emisión y el ajuste por riesgo de la celda | 16–17, 28 |
| Margen de tarifa de vida temporal | 10% del valor presente de las primas; 3% en edades 50+ por la competencia del canal bancario. Con esto el canal promocional es oneroso y las edades 50+ caen en RES | 16 |
| Estudio de mortalidad del reasegurador | Factor sobre CSO 1980 para edades 50+ con suma asegurada de USD 250.000 o más: 75% (2023), 115% (2024) y 85% (2025). El resto, 75%. Se combina con la experiencia propia por credibilidad | B41(c), B56–B57 |
| Retarificación 2025 | La tarifa de ese segmento pasa a 120% de CSO 1980 en 2025, por lo que la cohorte 2025 no tiene grupo oneroso | 16 |
| Experiencia de primas | Las diferencias entre primas esperadas y recibidas se tratan como servicio futuro y ajustan el CSM | B96(a) |
| Flujos de adquisición | Comisión del primer año más costo de suscripción. Las comisiones de renovación se tratan como gasto de mantenimiento | B65(e) |
| Recuperación de adquisición en el ingreso | Por paso del tiempo, ponderado por las pólizas en vigor esperadas | B125 |
| Componente de pérdida | Proporción fija: componente de pérdida entre valor presente de salidas más ajuste por riesgo al inicio del periodo, aplicada a los siniestros esperados, a la liberación del ajuste por riesgo y a las finanzas a tasa bloqueada | 50(a), 51–52 |
| CSM después de una reversión | Se reparte entre las unidades del periodo y las futuras, como en el Ejemplo 2A. El Ejemplo 8 del IASB lo reconoce todo en el año siguiente | 44(e), B119 |
| Compromiso de acreditación de vida con ahorro | HQM a un año del fin de año anterior menos 1,25%, con mínimo de 2,5%: 3,70% en 2023, 3,95% en 2024 y 3,40% en 2025. Las diferencias de acreditación y de tasas van a finanzas | B98–B100, B74(b), B97(a) |
| Capital del ajuste por riesgo de vida con ahorro | Se proyecta con la suma asegurada en vigor, porque las unidades de cobertura crecen con el valor de cuenta | B86–B88 |
| LIC de vida | Casos reportados más un IBNR igual a la mitad de los siniestros esperados de diciembre; no se descuenta porque se paga en semanas; ajuste por riesgo = 6% × LIC / 12 | 33, 37 |
| Índice de repuestos de flotas | 130% desde 2024, conocido por datos de mercado desde el cierre de 2024 | B44, 57 |
| Riesgo de incumplimiento del reasegurador | Las recuperaciones esperadas se reducen 0,4% (probabilidad 0,08% × severidad 60% × 8 años) | 63, 67 |
| Inversiones | Capital y fondos de vida temporal en bonos del Tesoro a 8 años a valor razonable con cambios en ORI; el resto en Tesoro corto a valor razonable con cambios en resultados | B129; NIIF 9 |
| Gastos de liquidación | 3% de la reserva de siniestros de daños | B65(f) |

### El guion de los tres cierres, tal como salió del motor

Los eventos de la sección 12 salen del motor; ningún importe está escrito a mano.

| Cierre | Grupo | Qué pasó | Importe (USD) | Párrafos |
| --- | --- | --- | --- | --- |
| 2023 | VT-2023-ONE | El canal promocional nace oneroso: pérdida inicial | 163.680 | 47, 49 |
| 2023 | RE-2023 | Ingreso por recuperación de pérdidas: 40% de la pérdida inicial y de su aumento posterior | 90.231 | 66A, B119D |
| 2023 | AUTO-2023-RES | Flotas cae en “resto” con ratio combinado esperado de 96,3% | — | 16, 18 |
| 2024 | VT-2023-RES y VT-2024-RES | El estudio de 115% agota su CSM: componentes de pérdida al cierre | 172.455 y 134.152 | 48, 49 |
| 2024 | AUTO-2024-RES | Con el índice de repuestos, los flujos de la cobertura restante superan el LRC | 19.115 | 57–58 |
| 2025 | VT-2023-RES | El estudio de 85% revierte la pérdida y reconstruye el CSM | CSM 383.868 | 50(b), 44(c) |
| 2025 | RE-2023 | El tratado revierte su recuperación en la misma proporción | −138.248 | 66(c)(ii) |
| 2025 | AUTO-2025-ONE | Flotas nace onerosa: ratio combinado esperado de 103,7% | — | 16(a), 18 |
| 2023–2025 | TRC | Elegible para el PAA en las tres cohortes; diferencia máxima con el GMM de 4,6%, en el escenario de tasas −100 pb | — | 53(a), 54 |

El componente de pérdida de VT-2023-ONE sube en 2024 y baja en 2025 por las mismas causas, pero nunca se agota, porque el descuento promocional sigue siendo mayor que el margen.

### Resultados de los cierres

Seguros Barú gana USD 0,6 millones en 2023, 2,0 millones en 2024 y 3,2 millones en 2025 antes de impuestos. El CSM de vida crece con cada cohorte y el reaseguro es un costo neto.

| USD | 2023 | 2024 | 2025 |
| --- | --: | --: | --: |
| Ingresos por seguros | 9.780.724 | 21.995.636 | 26.742.566 |
| Resultado del servicio de seguros, neto de reaseguro | 450.534 | 1.888.113 | 2.551.051 |
| Resultado financiero neto | 1.362.466 | 1.372.778 | 1.993.241 |
| Otros gastos no atribuibles (B66(d)) | (1.219.377) | (1.245.768) | (1.295.094) |
| Resultado antes de impuestos | 593.623 | 2.015.122 | 3.249.198 |
| Otro resultado integral | (580) | (1.162.526) | 885.255 |
| Patrimonio al 31 de diciembre | 20.593.043 | 21.445.639 | 25.580.091 |
| CSM de vida temporal | 2.726.015 | 4.785.364 | 10.836.220 |
| Componente de pérdida de vida temporal | 217.915 | 864.107 | 222.553 |
| CSM de vida con ahorro | 2.278.278 | 4.740.464 | 7.084.405 |
| CSM del reaseguro cedido (costo neto) | 983.949 | 1.738.210 | 4.017.491 |

El ORI de 2024 viene sobre todo de los bonos a valor razonable con cambios en ORI: las tasas subieron y su valor cayó. El pasivo de vida temporal casi no se mueve con las tasas, porque su valor presente neto es cercano a cero: las primas futuras compensan los siniestros futuros. Los niveles de confianza equivalentes del ajuste por riesgo (par. 119) son 88% en vida temporal (costo de capital) y 73% en el LIC de daños, una vez diversificado el percentil 75 de cada cobertura.

## Anexo A. IFRS 18: cómo cambiará la presentación desde 2027

IFRS 18 reemplaza a NIC 1 para periodos que empiezan el 1 de enero de 2027 o después, y se aplica de forma retroactiva, reexpresando el comparativo. Para Seguros Barú no cambia ninguna medición de IFRS 17: cambia cómo se ordena y se nombra el estado de resultados y qué se revela sobre él. Por eso los cierres 2023–2025 se presentan con NIC 1, y el proyecto añade una versión pro forma de 2025 con IFRS 18, con 2024 como comparativo reexpresado, para mostrar la transición.

### Qué introduce IFRS 18

- **Cinco categorías (IFRS 18.47).** Cada ingreso y gasto se clasifica como operativo, de inversión, de financiación, de impuesto sobre la renta o de operaciones discontinuadas.
- **Subtotales obligatorios (IFRS 18.69).** Resultado operativo y resultado antes de financiación e impuestos.
- **Actividad principal de inversión (IFRS 18.55–58, B31).** Una aseguradora invierte como parte de su actividad principal, así que los ingresos de sus inversiones van a la categoría operativa y no a la de inversión. Lo mismo ocurre con el efectivo y equivalentes (IFRS 18.56(a)).
- **Finanzas de seguros (IFRS 18.64, B58).** Los ingresos y gastos financieros de IFRS 17 reconocidos en resultados van siempre a la categoría operativa, tenga o no la entidad una actividad principal de inversión.
- **Gastos por naturaleza (IFRS 18.83).** Si los gastos se presentan por función, como las líneas que exige IFRS 17, una nota debe mostrar cuánto de cada línea es depreciación, amortización, beneficios a empleados, deterioro y rebajas de inventario.
- **Medidas de desempeño definidas por la gerencia (IFRS 18.117–123).** Son subtotales de ingresos y gastos que la gerencia comunica fuera de los estados y que la norma no define. Hay que describirlos y conciliarlos con el subtotal NIIF más parecido. Un ratio combinado no es una de estas medidas, porque no es un subtotal de ingresos y gastos.
- **Agrupación y desagregación (IFRS 18.41–43).** IFRS 17 ya remite a estos párrafos para decidir el nivel de detalle de sus revelaciones (IFRS 17, par. 96).
- **Estado de flujos de efectivo (NIC 7 modificada).** El método indirecto parte del resultado operativo y se eliminan las opciones para clasificar intereses y dividendos.

### El estado de resultados de Seguros Barú con IFRS 18

| Línea | Categoría con IFRS 18 | Base |
| --- | --- | --- |
| Ingresos por seguros | Operativa | IFRS 17, par. 83 |
| Gastos del servicio de seguros | Operativa | IFRS 17, par. 84 |
| Resultado neto del reaseguro cedido | Operativa | IFRS 17, par. 82 y 86 |
| Ingresos de inversiones del Tesoro y del efectivo | Operativa | IFRS 18.55–56 |
| Ingresos y gastos financieros de seguros emitidos y cedidos | Operativa | IFRS 18.64 |
| Gastos no atribuibles a contratos | Operativa | B66(d) de IFRS 17 |
| **Resultado operativo** | Subtotal obligatorio | IFRS 18.69 |
| Inversiones en asociadas o negocios conjuntos | Inversión (no hay) | IFRS 18, excepción para asociadas |
| **Resultado antes de financiación e impuestos** | Subtotal obligatorio; igual al operativo porque no hay partidas de inversión | IFRS 18.69 |
| Gastos por deuda | Financiación (no hay deuda) | IFRS 18.47 |
| Impuesto sobre la renta | Fuera del alcance | — |

Como Seguros Barú no tiene deuda, asociadas ni impuestos modelados, casi todo cae en la categoría operativa. La diferencia visible frente a NIC 1 es que el resultado operativo pasa a ser un subtotal definido y comparable entre aseguradoras.

### Qué añade el proyecto para mostrar la transición

1. **Estado pro forma.** El 2025 se presenta con las categorías y subtotales de IFRS 18, y el 2024 se reexpresa como comparativo.
2. **Conciliación de transición.** Cada línea del 2024 presentada con NIC 1 se concilia con su versión reexpresada con IFRS 18.
3. **Nota de gastos por naturaleza.** El simulador de gastos asigna una naturaleza a cada gasto (empleados, tecnología, comisiones, etc.) para poder preparar la nota de IFRS 18.83.
4. **Una medida de la gerencia ilustrativa (propuesta).** Resultado operativo ajustado, que excluye pérdidas y reversiones de grupos onerosos, con su conciliación al resultado operativo.

Fuentes: [KPMG, First Impressions IFRS 18](https://assets.kpmg.com/content/dam/kpmgsites/xx/pdf/ifrg/2024/isg-first-impressions-presentation-and-disclosure-ifrs-18.pdf), [SOA, IFRS 18: Introduction for Insurers](https://www.soa.org/sections/financial-reporting/financial-reporting-newsletter/2025/september/fr-2025-09-chng/), [Forvis Mazars, IFRS 18 for insurers](https://www.forvismazars.com/group/en/insights/latest-insights/ifrs-18-for-insurers) y [KPMG, Insurers: are you ready for IFRS 18? (mayo de 2026)](https://assets.kpmg.com/content/dam/kpmgsites/xx/pdf/ifrg/2026/isg-talkbook-insurers-are-you-ready-for-ifrs-18.pdf).

## Anexo B. Cómo se reconoce el ingreso en el BBA

En el modelo general (BBA o GMM), el ingreso por seguros no es la prima cobrada: es la parte de la contraprestación que corresponde al servicio prestado en el periodo. Se mide como la reducción del LRC por los servicios de ese periodo (par. 83, B123), y a lo largo de la vida del grupo suma exactamente las primas, ajustadas por financiación y sin componentes de inversión (B120).

### Los componentes del ingreso (B121–B125)

**Ingreso del periodo = siniestros y gastos esperados + liberación del ajuste por riesgo + liberación del CSM + recuperación de gastos de adquisición + otros**

1. **Siniestros y gastos esperados (B124(a)).** Se usan los importes que se esperaban al inicio del periodo, no los reales. Si los siniestros reales son mayores, el ingreso no cambia: la diferencia aparece en el gasto y reduce el resultado del servicio. Se excluyen la parte asignada al componente de pérdida, los pagos de componentes de inversión, los impuestos cobrados por cuenta de terceros y los gastos de adquisición.
2. **Liberación del ajuste por riesgo (B124(b)).** Es la parte del ajuste que se libera porque el riesgo del periodo ya pasó. No incluye los cambios por servicio futuro, que ajustan el CSM, ni lo asignado al componente de pérdida.
3. **Liberación del CSM (B124(c)).** Es la ganancia no devengada que corresponde al servicio del periodo, medida con las unidades de cobertura (siguiente apartado).
4. **Recuperación de gastos de adquisición (B125).** La parte de la prima que recupera esos gastos se asigna por el paso del tiempo, y el mismo importe se reconoce como gasto. Por eso los gastos de adquisición no afectan el resultado del periodo, solo su presentación.
5. **Otros (B124(d)).** Por ejemplo, ajustes por experiencia de primas que no se refieren a servicio futuro.

### Las unidades de cobertura (B119)

Las unidades de cobertura miden cuánto servicio presta el grupo en cada periodo, considerando para cada contrato la cantidad de beneficios y su periodo de cobertura esperado (B119(a)). El CSM se libera al final, después de sumar contratos nuevos, intereses y cambios de estimación del periodo (par. 44), y se reparte por igual entre las unidades del periodo y las futuras (B119(b)–(c)):

**Liberación del CSM del periodo = CSM antes de liberar × unidades del periodo ÷ (unidades del periodo + unidades futuras esperadas)**

En Seguros Barú, las unidades se definen así:

- **Vida temporal:** suma asegurada en vigor esperada. Baja con las muertes y caducidades esperadas, así que el CSM se libera más al principio, aunque la prima sea nivelada.
- **Vida con ahorro:** cargo esperado por riesgo de muerte más 1% del valor de cuenta. La segunda parte representa el servicio de retorno de inversión (B119B), que dura hasta que se paga el valor de cuenta a los asegurados actuales (B119A). La ponderación se revela según el par. 117(c)(v).
- **TRC, si va a GMM:** exposición esperada por avance de obra. Crece con el tiempo, así que el CSM se libera más al final.
- **Reaseguro cedido:** suma asegurada cedida en vigor, aplicada al servicio recibido (par. 66(e)).

**Descontar o no las unidades (propuesta: no descontar).** IFRS 17 no lo define, así que es una política que debe aplicarse de forma uniforme y revelarse. Descontar da menos peso a las unidades lejanas y libera el CSM un poco antes. En el ejemplo de abajo, con 5%, el primer año liberaría 43,4% del CSM en lugar de 41,7%.

### Ejemplo numérico

Un grupo de contratos de tres años cobra una prima única de 900 al inicio y paga 90 de comisiones. Espera siniestros de 200, 160 y 120, proporcionales a los contratos en vigor (100, 80 y 60, que son las unidades de cobertura). El ajuste por riesgo inicial es 30 y se libera en la misma proporción. Para aislar la mecánica del ingreso, la tasa de descuento es cero. El CSM inicial es 900 − 480 − 90 − 30 = 300. Los siniestros reales son 220, 160 y 110.

| Año | Siniestros esperados | Liberación del ajuste por riesgo | Liberación del CSM | Recuperación de adquisición | Ingreso por seguros | Gasto del servicio | Resultado del servicio | CSM al cierre |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 200,0 | 12,5 | 125,0 | 30,0 | 367,5 | 250,0 | 117,5 | 175,0 |
| 2 | 160,0 | 10,0 | 100,0 | 30,0 | 300,0 | 190,0 | 110,0 | 75,0 |
| 3 | 120,0 | 7,5 | 75,0 | 30,0 | 232,5 | 140,0 | 92,5 | 0,0 |
| Total | 480,0 | 30,0 | 300,0 | 90,0 | 900,0 | 580,0 | 320,0 | — |

El ingreso total es 900, igual a la prima, aunque toda se cobró el primer día: el resto queda en el LRC hasta que se presta el servicio. El resultado total de 320 es el CSM de 300 más el ajuste por riesgo de 30, menos 10 de experiencia desfavorable neta. En el año 1 los siniestros reales superan a los esperados en 20, pero el ingreso no se mueve: la desviación solo aparece en el gasto. El gasto incluye los siniestros reales más 30 de amortización de comisiones, el mismo importe que se recupera en el ingreso.

### Tres casos que cambian el cálculo

- **Grupo oneroso (par. 49–52, B123(b)).** Parte de los siniestros esperados que se liberan cada año se asigna al componente de pérdida y no al ingreso, porque esa pérdida ya se reconoció al inicio. El ingreso queda por debajo de los costos esperados, y el gasto muestra la reversión del componente de pérdida.
- **Vida con ahorro (par. 85, B120).** La parte de la prima que va al valor de cuenta y los rescates o vencimientos hasta el valor de rescate no pasan por ingresos ni gastos. El ingreso refleja solo la parte de los siniestros que excede el valor de rescate, los gastos, la liberación del ajuste por riesgo y del CSM.
- **PAA (B126).** En autos e incendio/hogar no hay CSM ni unidades de cobertura: el ingreso es la prima esperada asignada por el paso del tiempo, o por el patrón de siniestros si el riesgo no es uniforme.
