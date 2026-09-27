# Consumer Trend Screener

Google Trends의 변곡과 수출입·유통 신호를 결합해 소비재 투자 아이디어를 탐색하는 정적 대시보드입니다.

GitHub Pages는 `main` 브랜치의 `/docs` 폴더를 게시합니다.

## 자동 갱신

- GitHub Actions가 매일 07:27 KST에 실행됩니다.
- Google의 호출 제한을 피하기 위해 하루 2개 묶음을 순환 수집하며, 전체 브랜드는 약 6일마다 갱신됩니다.
- 수집이 실패한 묶음은 마지막 정상 데이터를 그대로 유지합니다.
- Google Trends 공식 API는 제한된 알파이므로 현재 수집기는 비공식 웹 자동화를 사용합니다.
