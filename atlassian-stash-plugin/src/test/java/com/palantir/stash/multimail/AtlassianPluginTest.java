//   Copyright 2013 Palantir Technologies
//
//   Licensed under the Apache License, Version 2.0 (the "License");
//   you may not use this file except in compliance with the License.
//   You may obtain a copy of the License at
//
//       http://www.apache.org/licenses/LICENSE-2.0
//
//   Unless required by applicable law or agreed to in writing, software
//   distributed under the License is distributed on an "AS IS" BASIS,
//   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//   See the License for the specific language governing permissions and
//   limitations under the License.
package com.palantir.stash.multimail;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.net.URL;
import java.util.Enumeration;

import junit.framework.Assert;

import org.apache.log4j.Logger;
import org.junit.Test;

public class AtlassianPluginTest {

    private static final Logger log = Logger.getLogger(AtlassianPluginTest.class.getName());

    private void testClass(ClassLoader cl, String s) {
        // skip strings that don't seem to be a class we care about
        if (!s.startsWith("com.palantir"))
            return;
        // skip this properties file
        if (s.contains("i18n_text"))
            return;

        String path = s;
        try {
            log.info("Testing class '" + s + "'");

            cl.loadClass(path);
        } catch (Exception e) {
            throw new RuntimeException("Unable to load class " + path, e);
        }
    }

    @Test
    public void testStringsInPluginXml() throws IOException, ClassNotFoundException {
        ClassLoader cl = this.getClass().getClassLoader();
        Enumeration<URL> resources = cl.getResources("atlassian-plugin.xml");

        URL atlassianPluginUrl = null;
        while (resources.hasMoreElements()) {
            URL u = resources.nextElement();
            // THis is how we make sure we get OUR atlassian-plugin.xml, not
            // someone else's
            if (!u.toString().endsWith("target/classes/atlassian-plugin.xml"))
                continue;
            atlassianPluginUrl = u;
            break;
        }

        Assert.assertNotNull(atlassianPluginUrl);
        InputStream pluginXml = atlassianPluginUrl.openStream();
        Assert.assertNotNull(pluginXml);

        int readCount = 0;
        char[] buf = new char[4096];
        StringBuffer sb = new StringBuffer();
        Reader reader = new BufferedReader(new InputStreamReader(pluginXml));
        try {
            while ((readCount = reader.read(buf)) != -1) {
                sb.append(buf, 0, readCount);
            }
        } finally {
            pluginXml.close();
            reader.close();
        }
        String xml = sb.toString();

        for (String s : xml.split("\"")) {
            // skip strings that don't seem to be a class we care about
            if (!s.startsWith("com.palantir") && !s.startsWith("com.atlassian"))
                continue;

            // classes are always camel-case (I hope! lulz)
            String[] temp = s.split("\\,");
            if (!temp[temp.length - 1].matches("^[A-Z]"))
                continue;

            // skip this properties file
            if (s.contains("i18n_text"))
                continue;

            try {
                cl.loadClass(s);
            } catch (Exception e) {
                throw new RuntimeException("Unable to load class " + s, e);
            } finally {
                reader.close();
            }
        }

        for (String s : xml.split("<|>")) {
            if (!s.startsWith("com.palantir") && !s.startsWith("com.atlassian"))
                continue;
            if (s.contains("i18n_text"))
                continue;

            testClass(cl, s);
        }
    }
}
