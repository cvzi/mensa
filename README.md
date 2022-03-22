# mensa
Parsers for openmensa.org. The parsers runs in a [Github action](https://github.com/cvzi/mensa/actions?query=workflow%3ARunParsers) and push the XML feeds to [Github pages](https://cvzi.github.io/mensa/)

Parsers support:
*   [Studierendenwerk Kaiserslautern](https://www.studierendenwerk-kaiserslautern.de/kaiserslautern/essen-und-trinken/)
*   [Kölner Studierendenwerk](https://www.kstw.de/speiseplan)
*   [mensen.at](https://www.mensen.at/)
*   [Wirtschaftsuniversität Wien](http://www.wumensa.at/)
*   [Restopolis](https://portal.education.lu/restopolis/) (luxembourgish school restaurants)
*   [ristocloud/markas](https://www.markas.com)
*   [mampf1a.de](https://mampf1a.de/)
*   [inetmenue.de](https://www.inetmenue.de/)
*   [Studierendenwerk Greifswald](https://www.stw-greifswald.de/essen/speiseplaene/) forked from [github.com/derconno/OpenMensaParserHOST](https://github.com/derconno/OpenMensaParserHOST)

|  Feeds       |                                         Status                                                                                                                  |                     Cron                                                                                                                                      |
|:------------:|:---------------------------------------------------------------------------------------------------------------------------------------------------------------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------:|
| today        | [![RunParsersToday](https://github.com/cvzi/mensa/workflows/RunParsersToday/badge.svg)](https://github.com/cvzi/mensa/actions?query=workflow%3ARunParsersToday) | [32 7-11 * * 1-5](https://crontab.guru/#32_7-11_*_*_1-5 "“At minute 32 past every hour from 7 through 11 on every day-of-week from Monday through Friday.” ") |
| all          | [![RunParsers](https://github.com/cvzi/mensa/workflows/RunParsers/badge.svg)](https://github.com/cvzi/mensa/actions?query=workflow%3ARunParsers)                | [12 6 * * *](https://crontab.guru/#12_6_*_*_* "“At 06:12.” ")                                                                                                 |

Links:
*   See the resulting feeds at [https://cvzi.github.io/mensa/](https://cvzi.github.io/mensa/)
*   [Understand OpenMensa’s Parser Concept](https://doc.openmensa.org/parsers/understand/)
*   OpenMensa [XML schema](https://doc.openmensa.org/feed/v2/)
*   OpenMensa Android app on [f-droid](https://f-droid.org/en/packages/de.uni_potsdam.hpi.openmensa/), [playstore](https://play.google.com/store/apps/details?id=de.uni_potsdam.hpi.openmensa), [github](https://github.com/domoritz/open-mensa-android)
*   My other parser for OpenMensa: [https://github.com/cvzi/mensahd](https://github.com/cvzi/mensahd)
*   Another parser by [TheNCuber](https://github.com/TheNCuber/) based on this parser: [https://github.com/TheNCuber/mensa](https://github.com/TheNCuber/mensa)
