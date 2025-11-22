package org.example;

import com.intellij.ide.DataManager;
import com.intellij.openapi.actionSystem.CommonDataKeys;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.components.Service;
import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.editor.Editor;
import com.intellij.openapi.editor.LogicalPosition;
import io.netty.bootstrap.ServerBootstrap;
import io.netty.buffer.Unpooled;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.handler.codec.http.*;
import io.netty.util.CharsetUtil;

import javax.swing.*;
import java.awt.*;
import java.net.InetSocketAddress;
import java.util.List;
import java.util.Map;

import org.json.JSONObject;

@Service(Service.Level.APP)
public final class HttpCoordinateServer {

    private static final Logger LOG = Logger.getInstance(HttpCoordinateServer.class);
    private static final int PORT = 5005;
    private EventLoopGroup bossGroup;
    private EventLoopGroup workerGroup;
    private Channel channel;

    private boolean isRunning = false;

    public HttpCoordinateServer() {
        LOG.info("HttpCoordinateServer service initialized. Starting Netty server...");

        ApplicationManager.getApplication().executeOnPooledThread(this::startServer);
    }

    public void startServer() {
        if (isRunning) {
            LOG.info("HTTP server is already running.");
            return;
        }

        bossGroup = new NioEventLoopGroup(1);
        workerGroup = new NioEventLoopGroup();

        try {
            ServerBootstrap b = new ServerBootstrap();

            b.group(bossGroup, workerGroup)
                    .channel(NioServerSocketChannel.class)
                    .childHandler(new ChannelInitializer<SocketChannel>() {
                        @Override
                        protected void initChannel(SocketChannel ch) {
                            ChannelPipeline p = ch.pipeline();
                            p.addLast(new HttpServerCodec());
                            p.addLast(new HttpObjectAggregator(65536));
                            p.addLast(new HttpCoordinateHandler());
                        }
                    })
                    .option(ChannelOption.SO_BACKLOG, 128)
                    .childOption(ChannelOption.SO_KEEPALIVE, true);

            ChannelFuture future = b.bind(PORT);

            channel = future.sync().channel();

            if (future.isSuccess()) {
                isRunning = true;
                LOG.info("Bound Address: " + ((InetSocketAddress)channel.localAddress()).getHostString()
                        + ":" + ((InetSocketAddress)channel.localAddress()).getPort());
            } else {
                stopServer();
            }

        } catch (Exception e) {
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

    private static class HttpCoordinateHandler extends SimpleChannelInboundHandler<FullHttpRequest> {

        @Override
        protected void channelRead0(ChannelHandlerContext ctx, FullHttpRequest request) {
            QueryStringDecoder decoder = new QueryStringDecoder(request.uri());
            Map<String, List<String>> parameters = decoder.parameters();

            if (!decoder.path().equals("/")) {
                sendError(ctx, HttpResponseStatus.NOT_FOUND);
                return;
            }

            String xStr = getFirstValue(parameters, "x");
            String yStr = getFirstValue(parameters, "y");

            if (xStr == null || yStr == null) {
                sendError(ctx, HttpResponseStatus.BAD_REQUEST);
                return;
            }

            try {
                int x = Integer.parseInt(xStr);
                int y = Integer.parseInt(yStr);

                final int[] lineNumberHolder = { -1 };
                final StringBuilder fileTextHolder = new StringBuilder();

                ApplicationManager.getApplication().invokeAndWait(() -> {
                    Editor editor = CommonDataKeys.EDITOR.getData(DataManager.getInstance().getDataContext());
                    if (editor == null) {
                        return;
                    }

                    JComponent editorComponent = editor.getContentComponent();
                    Point screenPoint = new Point(x, y);
                    SwingUtilities.convertPointFromScreen(screenPoint, editorComponent);

                    LogicalPosition pos = editor.xyToLogicalPosition(screenPoint);
                    lineNumberHolder[0] = pos.line;

                    fileTextHolder.append(editor.getDocument().getText());
                });

                // Build JSON response
                String jsonResponse = "{ \"lineNumber\": " + lineNumberHolder[0] +
                        ", \"fileText\": " + JSONObject.quote(fileTextHolder.toString()) + " }";

                sendResponse(ctx, HttpResponseStatus.OK, jsonResponse);

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