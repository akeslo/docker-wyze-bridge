docker buildx build -t wyze-bridge-test -f docker/Dockerfile . --build-arg BUILD=test --build-arg BUILD_DATE=today --build-arg GITHUB_SHA=NA --platform=linux/amd64

docker run -i -t --rm \
--network bridge \
-p 1935:1935 \
-p 1936:1936 \
-p 2935:2935 \
-p 2936:2936 \
-p 8000:8000/udp \
-p 8001:8001/udp \
-p 8002:8002/udp \
-p 8003:8003/udp \
-p 8189:8189/udp \
-p 8189:8189 \
-p 8322:8322 \
-p 8554:8554 \
-p 8888:8888 \
-p 8889:8889 \
-p 8890:8890/udp \
-p 5000:5000 \
--mount type=bind,src=./media,dst=/media --env-file ./test_env.list wyze-bridge-test