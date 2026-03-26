package com.scue.bridge;

import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.InetSocketAddress;
import java.util.Collections;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * WebSocket server that broadcasts JSON messages to all connected Python clients
 * and routes incoming command messages to the CommandHandler.
 */
public class BridgeWebSocketServer extends WebSocketServer {

    private static final Logger log = LoggerFactory.getLogger(BridgeWebSocketServer.class);
    private final Set<WebSocket> clients = Collections.newSetFromMap(new ConcurrentHashMap<>());
    private CommandHandler commandHandler;

    public BridgeWebSocketServer(int port) {
        super(new InetSocketAddress("localhost", port));
        setReuseAddr(true);
    }

    /**
     * Set the command handler for processing incoming messages.
     * Must be called after construction, before commands are expected.
     */
    public void setCommandHandler(CommandHandler handler) {
        this.commandHandler = handler;
    }

    @Override
    public void onOpen(WebSocket conn, ClientHandshake handshake) {
        clients.add(conn);
        log.info("Client connected ({} total)", clients.size());
    }

    @Override
    public void onClose(WebSocket conn, int code, String reason, boolean remote) {
        clients.remove(conn);
        log.warn("Client disconnected ({} total)", clients.size());
    }

    @Override
    public void onMessage(WebSocket conn, String message) {
        if (commandHandler != null) {
            commandHandler.handleCommand(message);
        } else {
            log.warn("Received message but no CommandHandler registered: {}", message);
        }
    }

    @Override
    public void onError(WebSocket conn, Exception ex) {
        if (conn != null) {
            clients.remove(conn);
        }
        log.error("WebSocket error: {}", ex.getMessage(), ex);
    }

    @Override
    public void onStart() {
        log.info("WebSocket server started on port {}", getPort());
    }

    /**
     * Broadcast a JSON message to all connected clients.
     */
    public void broadcastMessage(String json) {
        for (WebSocket client : clients) {
            try {
                if (client.isOpen()) {
                    client.send(json);
                }
            } catch (Exception e) {
                log.warn("Failed to send to client: {}", e.getMessage());
                clients.remove(client);
            }
        }
    }

    public int getClientCount() {
        return clients.size();
    }
}
