package com.palantir.stash.multimail.logger;

import java.io.InputStream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.joran.JoranConfigurator;
import ch.qos.logback.core.joran.spi.JoranException;

/**
 * Programmatically configure our logging.
 *
 * For details, see: http://logback.qos.ch/manual/configuration.html
 *
 * @author cmyers
 *
 */
public class PluginLoggerFactory {

    private static final String ROOT = "com.palantir.stash.multimail";
    private static final Logger stashRootLogger = LoggerFactory.getLogger("ROOT");

    private final LoggerContext context;

    public PluginLoggerFactory() {
        // Assumes LSF4J is bound to logback
        context = (LoggerContext) LoggerFactory.getILoggerFactory();

        JoranConfigurator configurator = new JoranConfigurator();
        configurator.setContext(context);

        InputStream is;
        is = this.getClass().getClassLoader().getResourceAsStream("logback-test.xml");
        if (is != null) {
            stashRootLogger.info("Using logback-test.xml for logger settings");
        } else {
            stashRootLogger.info("Using logback.xml for logger settings");
            is = this.getClass().getClassLoader().getResourceAsStream("logback.xml");
        }

        try {
            configurator.doConfigure(is);
        } catch (JoranException e) {
            System.err.println("Error configuring logging framework" + e.toString());
        }
    }

    public Logger getLogger() {
        return getLogger(ROOT);
    }

    public Logger getLogger(String name) {
        return context.getLogger(name);
    }

    public Logger getLogger(Class<? extends Object> clazz) {
        String className = clazz.toString();
        if (className.startsWith("class ")) {
            className = className.replaceFirst("class ", "");
        }

        return context.getLogger(className);

    }

    public Logger getLoggerForThis(Object obj) {
        String className = obj.getClass().toString();
        if (className.startsWith("class ")) {
            className = className.replaceFirst("class ", "");
        }

        return context.getLogger(className);

    }
}
