docker buildx build -t wyze-bridge-test -f docker/Dockerfile . --build-arg BUILD=test --build-arg BUILD_DATE=today --build-arg GITHUB_SHA=NA --platform=linux/amd64

docker run \
-p 1935:1935 \
-p 1936:1936 \
-p 2935:2935 \
-p 2936:2936 \
-p 8000:8000/udp \
-p 8001:8001/udp \
-p 8002:8002/udp \
-p 8003:8003/udp \
-p 8189:8189/udp \
-p 8322:8322 \
-p 8554:8554 \
-p 8888:8888 \
-p 8889:8889 \
-p 8890:8890/udp \
-p 5000:5000 \
-p 9996:9996 \
-p 9997:9997 \
-p 9998:9998 \
-p 9999:9999 \
--env-file ./test_env.list -i -t wyze-bridge-test