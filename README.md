Текущий этап выполнения: Лабораторная работа №2

Готовы: auth_service/, catalog_service/, compose.yaml, nginx.conf

Пройденные тесты:
1. Регистрация пользователя (POST /register) -> 200, User registered successfully
2. /me с валидным токеном -> 200, username + приветствие
3. /me с поддельным токеном -> 401, Could not validate credentials
4. Обновление цели (PUT /goals/{id}) -> 200, изменённые поля
5. Повторное удаление -> 404, Goal not found
6. Все контейнеры запущены (docker compose ps) -> 6 контейнеров running
7. Балансировка нагрузки -> чередование catalog-1 / catalog-2
8. Отказоустойчивость (docker stop catalog-1) -> все запросы на catalog-2

