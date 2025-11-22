package org.example;

import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.components.Service;
import com.intellij.openapi.diagnostic.Logger;
import io.netty.bootstrap.ServerBootstrap;
import io.netty.buffer.Unpooled;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.handler.codec.http.*;
import io.netty.util.CharsetUtil;

import java.util.List;
import java.util.Map;

@Service(Service.Level.APP)
public final class HttpCoordinateServer {

    private static final Logger LOG = Logger.getInstance(HttpCoordinateServer.class);
    private static final int PORT = 5005;
    private EventLoopGroup bossGroup;
    private EventLoopGroup workerGroup;
    private Channel channel;

    public HttpCoordinateServer() {
        LOG.info("HttpCoordinateServer service initialized. Starting Netty server...");

        ApplicationManager.getApplication().executeOnPooledThread(this::startServer);
    }

    public void startServer() {
        if (channel != null && channel.isOpen()) {
            LOG.info("HTTP server is already running.");
            return;
        }

        bossGroup = new NioEventLoopGroup(1); // Accept incoming connections
        workerGroup = new NioEventLoopGroup(); // Handle traffic of the accepted connections

        try {
            ServerBootstrap b = new ServerBootstrap();
            b.group(bossGroup, workerGroup)
                    .channel(NioServerSocketChannel.class)
                    .childHandler(new ChannelInitializer<SocketChannel>() {
                        @Override
                        protected void initChannel(SocketChannel ch) {
                            ChannelPipeline p = ch.pipeline();
                            p.addLast(new HttpServerCodec());
                            p.addLast(new HttpObjectAggregator(65536)); // To aggregate fragmented HTTP messages
                            p.addLast(new HttpCoordinateHandler());
                        }
                    })
                    .option(ChannelOption.SO_BACKLOG, 128)
                    .childOption(ChannelOption.SO_KEEPALIVE, true);

            // Bind and start to accept incoming connections.
            channel = b.bind(PORT).sync().channel();
            LOG.info("✅ HTTP server started on port " + PORT);

        } catch (InterruptedException e) {
            LOG.error("Failed to start HTTP server", e);
            stopServer();
        }
    }

    public void stopServer() {
        LOG.info("Stopping HTTP server...");
        if (channel != null) {
            channel.close();
            channel = null;
        }
        if (bossGroup != null) bossGroup.shutdownGracefully();
        if (workerGroup != null) workerGroup.shutdownGracefully();
        LOG.info("HTTP server stopped.");
    }

    // Inner class to handle HTTP requests
    private static class HttpCoordinateHandler extends SimpleChannelInboundHandler<FullHttpRequest> {

        @Override
        protected void channelRead0(ChannelHandlerContext ctx, FullHttpRequest request) {
            QueryStringDecoder decoder = new QueryStringDecoder(request.uri());
            Map<String, List<String>> parameters = decoder.parameters();

            // 1. Check Path: Only handle requests to the root path
            if (!decoder.path().equals("/")) {
                sendError(ctx, HttpResponseStatus.NOT_FOUND);
                return;
            }

            // 2. Extract parameters
            String xStr = getFirstValue(parameters, "x");
            String yStr = getFirstValue(parameters, "y");

            if (xStr == null || yStr == null) {
                sendError(ctx, HttpResponseStatus.BAD_REQUEST);
                return;
            }

            try {
                int x = Integer.parseInt(xStr);
                int y = Integer.parseInt(yStr);

                // 3. Execute action on the EDT
                ApplicationManager.getApplication().invokeLater(() -> {
                    PrintLineAction.handleCoordinates(x, y);
                });

                // 4. Send success response
                sendResponse(ctx, HttpResponseStatus.OK, "OK. Line copied.");

            } catch (NumberFormatException e) {
                sendError(ctx, HttpResponseStatus.BAD_REQUEST);
            }
        }

        private String getFirstValue(Map<String, List<String>> parameters, String key) {
            List<String> values = parameters.get(key);
            return values != null && !values.isEmpty() ? values.get(0) : null;
        }

        private void sendResponse(ChannelHandlerContext ctx, HttpResponseStatus status, String content) {
            FullHttpResponse response = new DefaultFullHttpResponse(
                    HttpVersion.HTTP_1_1,
                    status,
                    Unpooled.copiedBuffer(content, CharsetUtil.UTF_8));

            response.headers().set(HttpHeaderNames.CONTENT_TYPE, "text/plain; charset=UTF-8");
            response.headers().setInt(HttpHeaderNames.CONTENT_LENGTH, response.content().readableBytes());

            ctx.writeAndFlush(response).addListener(ChannelFutureListener.CLOSE);
        }

        private void sendError(ChannelHandlerContext ctx, HttpResponseStatus status) {
            sendResponse(ctx, status, "Failure: " + status.reasonPhrase());
        }
    }
}